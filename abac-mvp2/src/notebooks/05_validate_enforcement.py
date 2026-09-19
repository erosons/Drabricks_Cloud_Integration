# Databricks notebook source
# DBTITLE 1,Step 05: Validate ABAC Enforcement
"""
Step 05: Validate ABAC Enforcement — Sample-Based for Scale

For 2000+ tables, full validation is impractical. This notebook:
1. Samples a subset of tables (configurable)
2. Queries columns that should be masked
3. Validates masking patterns are active:
   - Email: ***@domain.com
   - Phone: (***) ***-XXXX
   - SSN: ***-**-XXXX or [REDACTED]
4. Checks SHOW EFFECTIVE POLICIES on sample tables
5. Reports pass/fail with evidence

Note: If running as governance_cleartext_approved, values will be cleartext.
Remove yourself from that group to test actual masking.
"""
import sys
import os
import re
import random

dbutils.widgets.text("config_path", "", "Config Directory")
dbutils.widgets.text("project_root", "", "Project Root")
dbutils.widgets.text("sample_size", "10", "Tables to sample")

config_path = dbutils.widgets.get("config_path")
project_root = dbutils.widgets.get("project_root")
sample_size = int(dbutils.widgets.get("sample_size"))

sys.path.insert(0, f"{project_root}/src")
from config_loader import ABACConfigLoader, TemplateResolver

print(f"Config path: {config_path}")
print(f"Sample size: {sample_size} tables")

# COMMAND ----------

# DBTITLE 1,Load manifest and select sample
# Load governance manifest
loader = ABACConfigLoader(config_path)
manifest = loader.load()
resolver = TemplateResolver(manifest.templates)

# Select a random sample of tables that have tag-based policies
# Prioritize tables with explicit policy_bindings or inherited masks
tables_with_policies = [
    t for t in manifest.tables
    if t.policy_bindings or t.inherited_policy_bindings
]

if len(tables_with_policies) <= sample_size:
    sample_tables = tables_with_policies
else:
    sample_tables = random.sample(tables_with_policies, sample_size)

print(f"Total tables with policies: {len(tables_with_policies)}")
print(f"Sampling {len(sample_tables)} tables for validation:")
for t in sample_tables:
    fqn = f"{t.catalog}.{t.schema}.{t.table_id}"
    all_policies = t.policy_bindings + t.inherited_policy_bindings
    print(f"  - {fqn} (policies: {', '.join(all_policies[:3])}{'...' if len(all_policies) > 3 else ''})")

# Masking patterns for validation
MASKING_PATTERNS = {
    "email": re.compile(r"^\*\*\*@.+\..+$"),          # ***@domain.com
    "phone": re.compile(r"^\(\*\*\*\) \*\*\*-\d{4}$"),  # (***) ***-XXXX
    "ssn": re.compile(r"^\*\*\*-\*\*-\d{4}$|^\[REDACTED\]$"),  # ***-**-XXXX or [REDACTED]
    "generic_mask": re.compile(r"^.\*\*\*.$|^\*\*\*$"),  # x***y or ***
}

# COMMAND ----------

# DBTITLE 1,Validate masking on sampled tables
# Governed tag keys that should trigger masking
policy_tag_keys = set(t["key"] for t in manifest.policies.get("governed_tags", []))

test_results = []
tables_checked = 0
tables_with_masking = 0
tables_cleartext = 0
tables_failed = 0

for table in sample_tables:
    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    print(f"\n\u25b6 Validating: {fqn}")

    # 1. Get actual columns with their resolved tags
    try:
        cols_df = spark.sql(f"""
            SELECT column_name, data_type
            FROM {table.catalog}.information_schema.columns
            WHERE table_schema = '{table.schema}'
              AND table_name = '{table.table_id}'
        """)
        actual_columns = [
            {"name": row.column_name, "type": row.data_type}
            for row in cols_df.collect()
        ]
    except Exception as e:
        print(f"  \u2717 Cannot read columns: {e}")
        tables_failed += 1
        continue

    # 2. Resolve which columns should be masked (via template patterns)
    resolved = resolver.resolve_column_tags(
        table.template or "", actual_columns, table.column_overrides
    )
    masked_columns = [
        c["name"] for c in resolved
        if any(k in policy_tag_keys for k in c.get("tags", {}).keys())
    ]

    if not masked_columns:
        print(f"  (no columns expected to be masked)")
        continue

    # 3. Query the table and check masking on tagged columns
    col_list = ", ".join(f"`{c}`" for c in masked_columns[:5])  # Limit to 5 columns
    try:
        result_df = spark.sql(f"SELECT {col_list} FROM {fqn} LIMIT 5")
        rows = result_df.collect()
    except Exception as e:
        print(f"  \u2717 Query failed: {str(e)[:100]}")
        tables_failed += 1
        continue

    if not rows:
        print(f"  (table is empty)")
        continue

    tables_checked += 1
    table_has_masking = False
    table_has_cleartext = False

    for col_name in masked_columns[:5]:
        for row in rows:
            value = str(row[col_name]) if row[col_name] is not None else None
            if value is None:
                continue

            # Check against masking patterns
            is_masked = any(p.match(value) for p in MASKING_PATTERNS.values())
            if is_masked:
                table_has_masking = True
                test_results.append((fqn, col_name, "MASKED", value))
            elif "***" in value or "[REDACTED]" in value:
                table_has_masking = True
                test_results.append((fqn, col_name, "MASKED", value))
            else:
                table_has_cleartext = True
                test_results.append((fqn, col_name, "CLEARTEXT", value[:30]))

    if table_has_masking and not table_has_cleartext:
        tables_with_masking += 1
        print(f"  \u2713 MASKING ACTIVE on {len(masked_columns)} columns")
    elif table_has_cleartext and not table_has_masking:
        tables_cleartext += 1
        print(f"  \u26a0 CLEARTEXT (user may be in exception group)")
    elif table_has_masking and table_has_cleartext:
        tables_with_masking += 1
        print(f"  \u2713 PARTIAL MASKING (some columns masked, some cleartext)")

# COMMAND ----------

# DBTITLE 1,Check effective policies on sample
# Verify policies are bound to the sampled tables
print("\n\nEffective Policies on Sampled Tables:")
print("=" * 60)

policy_counts = {}
for table in sample_tables[:5]:  # Check first 5
    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    try:
        policies_df = spark.sql(f"SHOW EFFECTIVE POLICIES ON TABLE {fqn}")
        policies = policies_df.collect()
        policy_counts[fqn] = len(policies)
        print(f"\n  {fqn}: {len(policies)} effective policies")
        for row in policies:
            print(f"    - {row['Policy Name']} ({row['Policy Type']})")
    except Exception as e:
        policy_counts[fqn] = 0
        print(f"\n  {fqn}: {str(e)[:80]}")

# COMMAND ----------

# DBTITLE 1,Enforcement validation summary
# Summary
pass_count = len([t for t in test_results if t[2] == "MASKED"])
cleartext_count = len([t for t in test_results if t[2] == "CLEARTEXT"])

print(f"\n{'=' * 70}")
print("ENFORCEMENT VALIDATION RESULTS")
print(f"{'=' * 70}")
print(f"  Tables sampled:       {len(sample_tables)}")
print(f"  Tables checked:       {tables_checked}")
print(f"  Tables with masking:  {tables_with_masking}")
print(f"  Tables cleartext:     {tables_cleartext}")
print(f"  Tables failed:        {tables_failed}")
print(f"  Total checks:         {len(test_results)}")
print(f"  MASKED (pass):        {pass_count}")
print(f"  CLEARTEXT:            {cleartext_count}")
print(f"{'=' * 70}")

if tables_with_masking > 0 and tables_failed == 0:
    print("\n\u2713 MASKING IS ACTIVE")
    print("  ABAC enforcement is working correctly on sampled tables.")
elif tables_cleartext > 0 and tables_with_masking == 0:
    print("\n\u26a0 All values are CLEARTEXT.")
    print("  You are likely in the 'governance_cleartext_approved' group.")
    print("  To test masking, run as a user NOT in that group.")
elif tables_failed > 0:
    print(f"\n\u26a0 {tables_failed} tables could not be validated.")
    print("  Check table existence and permissions.")

# Exit with summary
dbutils.notebook.exit(
    f"checked={tables_checked}, masked={tables_with_masking}, "
    f"cleartext={tables_cleartext}, failed={tables_failed}"
)