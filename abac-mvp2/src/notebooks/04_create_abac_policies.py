# Databricks notebook source
# DBTITLE 1,Step 04: Create ABAC Policies (Parallelized)
"""
Step 04: Create ABAC Policies — Scalable for 2000+ Tables

Reads policy_bindings from the multi-file securables config at CATALOG,
SCHEMA, and TABLE levels, then looks up each policy in policies.yaml
to generate CREATE OR REPLACE POLICY statements.

MVP2 improvements:
- Collects bindings from multi-file config (not single securables.yaml)
- Includes inherited bindings resolved via templates
- Generates policies in parallel for scale
- Supports all scope levels: CATALOG, SCHEMA, TABLE
"""
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

dbutils.widgets.text("config_path", "", "Config Directory")
dbutils.widgets.text("project_root", "", "Project Root")

config_path = dbutils.widgets.get("config_path")
project_root = dbutils.widgets.get("project_root")

sys.path.insert(0, f"{project_root}/src")
from config_loader import ABACConfigLoader

print(f"Config path: {config_path}")

# COMMAND ----------

# DBTITLE 1,Load manifest and build policy lookup
# Load the governance manifest
loader = ABACConfigLoader(config_path)
manifest = loader.load()

# UDF location
udf_registry = manifest.policies["udf_registry"]
udf_prefix = f"{udf_registry['target_catalog']}.{udf_registry['target_schema']}"

# Build policy lookup: policy_id -> full definition
policy_lookup = {}
for policy in manifest.policies.get("policies", {}).get("row_filters", []):
    policy_lookup[policy["policy_id"]] = {**policy, "policy_type": "row_filter"}
for policy in manifest.policies.get("policies", {}).get("column_masks", []):
    policy_lookup[policy["policy_id"]] = {**policy, "policy_type": "column_mask"}

print(f"UDF location: {udf_prefix}")
print(f"Policy registry: {len(policy_lookup)} policies")
for pid, pdef in policy_lookup.items():
    print(f"  {pid} ({pdef['policy_type']}, scope={pdef['scope_level']}, udf={pdef['udf']})")
print(f"\nTables in manifest: {manifest.stats['total_tables']}")

# COMMAND ----------

# DBTITLE 1,Collect all policy bindings from all levels
# Walk all levels and collect (scope_type, target_fqn, policy_id)
bindings = []

# 1. Catalog-level bindings
for cat in manifest.catalogs:
    for policy_id in cat.get("policy_bindings", []):
        bindings.append(("CATALOG", cat["catalog_id"], policy_id))

# 2. Schema-level bindings
for sch in manifest.schemas:
    schema_fqn = f"{sch['catalog']}.{sch['schema_id']}"
    for policy_id in sch.get("policy_bindings", []):
        bindings.append(("SCHEMA", schema_fqn, policy_id))

# 3. Table-level bindings (explicit from table config files)
for table in manifest.tables:
    table_fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    for policy_id in table.policy_bindings:
        bindings.append(("TABLE", table_fqn, policy_id))

# Deduplicate (same policy can't bind to same target twice)
seen = set()
unique_bindings = []
for b in bindings:
    key = (b[0], b[1], b[2])
    if key not in seen:
        seen.add(key)
        unique_bindings.append(b)

bindings = unique_bindings

print(f"\nTotal policy bindings: {len(bindings)}")
print("=" * 60)
by_scope = {}
for scope_type, fqn, pid in bindings:
    by_scope.setdefault(scope_type, []).append((fqn, pid))

for scope, items in by_scope.items():
    print(f"  {scope}: {len(items)} bindings")
    for fqn, pid in items[:5]:
        print(f"    {fqn} <- {pid}")
    if len(items) > 5:
        print(f"    ... and {len(items) - 5} more")

# COMMAND ----------

# DBTITLE 1,SQL builder for CREATE POLICY
def build_create_policy_sql(policy_id, policy_def, scope_type, securable_fqn):
    """
    Generate CREATE OR REPLACE POLICY SQL from a policies.yaml definition.
    
    Supports both ROW FILTER and COLUMN MASK policies with:
    - TO / EXCEPT principal clauses
    - MATCH COLUMNS with tag-based conditions
    - USING COLUMNS for UDF parameter binding
    """
    policy_type = policy_def["policy_type"]
    udf_name = f"{udf_prefix}.{policy_def['udf']}"
    description = policy_def.get("description", "").replace("'", "''")

    # Principals (TO / EXCEPT)
    to_principals = policy_def.get("principals", {}).get("to", [])
    except_principals = policy_def.get("principals", {}).get("except", [])
    to_clause = ", ".join(to_principals)
    # Filter out template patterns with {}
    except_clause = ", ".join(p for p in except_principals if "{" not in p)

    # Match columns and conditions
    match_columns = policy_def.get("match_columns", [])
    using_columns = policy_def.get("using_columns", [])

    # Build SQL
    lines = [f"CREATE OR REPLACE POLICY {policy_id}"]
    lines.append(f"ON {scope_type} {securable_fqn}")
    lines.append(f"COMMENT '{description}'")

    if policy_type == "row_filter":
        lines.append(f"ROW FILTER {udf_name}")
    else:
        lines.append(f"COLUMN MASK {udf_name}")

    lines.append(f"TO {to_clause}")
    if except_clause:
        lines.append(f"EXCEPT {except_clause}")
    lines.append("FOR TABLES")

    # MATCH COLUMNS clause
    if match_columns:
        match_parts = []
        for mc in match_columns:
            condition = mc["condition"]
            alias = mc.get("alias", "")
            if alias:
                match_parts.append(f"{condition} AS {alias}")
            else:
                match_parts.append(condition)
        lines.append(f"MATCH COLUMNS ({', '.join(match_parts)})")

    # ON COLUMN (for column masks)
    if policy_type == "column_mask" and policy_def.get("on_column"):
        lines.append(f"ON COLUMN {policy_def['on_column']}")

    # USING COLUMNS
    if using_columns:
        lines.append(f"USING COLUMNS ({', '.join(using_columns)})")

    return "\n".join(lines)

# COMMAND ----------

# DBTITLE 1,Dry run — preview generated SQL
# Preview SQL (no changes made)
print("DRY RUN: Generated SQL statements")
print("=" * 60)

skip_count = 0
for scope_type, securable_fqn, policy_id in bindings[:10]:  # Show first 10
    if policy_id not in policy_lookup:
        skip_count += 1
        continue

    policy_def = policy_lookup[policy_id]
    try:
        sql = build_create_policy_sql(policy_id, policy_def, scope_type, securable_fqn)
        print(f"\n  \u25b6 {policy_id} ({policy_def['policy_type']}) -> {scope_type} {securable_fqn}")
        print(f"  {'-' * 56}")
        for line in sql.split("\n"):
            print(f"    {line}")
    except Exception as e:
        print(f"\n  \u2717 {policy_id}: {str(e)[:200]}")

if len(bindings) > 10:
    print(f"\n  ... and {len(bindings) - 10} more bindings")
if skip_count:
    print(f"\n  \u26a0 {skip_count} policy_ids not found in policies.yaml")

# COMMAND ----------

# DBTITLE 1,Execute policies in parallel
# Execute all policy statements
max_workers = manifest.controls.get("reconciliation", {}).get("max_parallel_workers", 20)

deployed = []
failed = []
skipped = []

print(f"\nCreating {len(bindings)} ABAC policies (max {max_workers} parallel)...")
print("=" * 60)

def create_policy(binding):
    scope_type, securable_fqn, policy_id = binding
    if policy_id not in policy_lookup:
        return ("skipped", policy_id, securable_fqn, "not in policies.yaml")
    policy_def = policy_lookup[policy_id]
    try:
        sql = build_create_policy_sql(policy_id, policy_def, scope_type, securable_fqn)
        spark.sql(sql)
        return ("success", policy_id, securable_fqn, None)
    except Exception as e:
        return ("failed", policy_id, securable_fqn, str(e)[:200])

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(create_policy, b): b for b in bindings}
    for future in as_completed(futures):
        status, policy_id, fqn, error = future.result()
        if status == "success":
            deployed.append(policy_id)
            print(f"  \u2713 {policy_id} -> {fqn}")
        elif status == "skipped":
            skipped.append(policy_id)
            print(f"  \u23ed {policy_id} -- skipped ({error})")
        else:
            failed.append((policy_id, error))
            print(f"  \u2717 {policy_id}: {error[:100]}")

print(f"\n{'=' * 60}")
print(f"Deployed: {len(deployed)} | Skipped: {len(skipped)} | Failed: {len(failed)}")

# COMMAND ----------

# DBTITLE 1,Verify with SHOW POLICIES and exit
# Verify policies were created
print("\nVerification: SHOW POLICIES")
print("=" * 60)

checked = set()
for scope_type, securable_fqn, _ in bindings:
    key = f"{scope_type} {securable_fqn}"
    if key in checked:
        continue
    checked.add(key)

    try:
        result = spark.sql(f"SHOW POLICIES ON {scope_type} {securable_fqn}").collect()
        if result:
            print(f"\n  {scope_type} {securable_fqn}:")
            for row in result:
                print(f"    - {row['name']} ({row['type']})")
        else:
            print(f"\n  {scope_type} {securable_fqn}: (no policies)")
    except Exception as e:
        print(f"\n  {scope_type} {securable_fqn}: {str(e)[:80]}")

# Final summary
if failed:
    print(f"\n\u2717 {len(failed)} policies failed:")
    for pid, err in failed:
        print(f"    - {pid}: {err}")
    raise Exception(f"POLICY DEPLOYMENT HAD {len(failed)} FAILURE(S)")

print(f"\n\u2713 All {len(deployed)} ABAC policies created successfully")
dbutils.notebook.exit(f"deployed={len(deployed)}, skipped={len(skipped)}, failed={len(failed)}")