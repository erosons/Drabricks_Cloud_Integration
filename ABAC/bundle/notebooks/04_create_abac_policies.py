# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Overview
# MAGIC %md
# MAGIC # Step 4: Create ABAC Policies
# MAGIC
# MAGIC Reads `securables.yaml` to identify `policy_bindings` at **catalog**, **schema**, and **table** levels, then looks up each policy's definition in `policies.yaml` to generate and execute `CREATE OR REPLACE POLICY` statements.
# MAGIC
# MAGIC **Cells:**
# MAGIC 1. Setup & imports
# MAGIC 2. Load configurations
# MAGIC 3. Build policy lookup
# MAGIC 4. Collect bindings from securables
# MAGIC 5. SQL builder function
# MAGIC 6. Dry-run (preview SQL)
# MAGIC 7. Execute policies
# MAGIC 8. Verify with SHOW POLICIES

# COMMAND ----------

# DBTITLE 1,Setup & Imports
import yaml
import os

dbutils.widgets.text("config_path", "/Workspace/Users/samson.eromonsei@databricks.com/ABAC/configs", "Config Directory")
config_path = dbutils.widgets.get("config_path")

# COMMAND ----------

# DBTITLE 1,Load Configurations
with open(os.path.join(config_path, "policies.yaml"), "r") as f:
    policies_config = yaml.safe_load(f)

with open(os.path.join(config_path, "securables.yaml"), "r") as f:
    securables_config = yaml.safe_load(f)

udf_registry = policies_config["udf_registry"]
udf_catalog = udf_registry["target_catalog"]
udf_schema = udf_registry["target_schema"]
udf_prefix = f"{udf_catalog}.{udf_schema}"

print(f"UDF location: {udf_prefix}")
print(f"Policies: {len(policies_config['policies']['row_filters'])} row filters, {len(policies_config['policies']['column_masks'])} column masks")

# COMMAND ----------

# DBTITLE 1,Build Policy Lookup
# Dictionary of policy_id -> full policy definition
policy_lookup = {}

for policy in policies_config["policies"]["row_filters"]:
    policy_lookup[policy["policy_id"]] = {**policy, "policy_type": "row_filter"}

for policy in policies_config["policies"]["column_masks"]:
    policy_lookup[policy["policy_id"]] = {**policy, "policy_type": "column_mask"}

print(f"Policy registry: {len(policy_lookup)} policies")
for pid, pdef in policy_lookup.items():
    print(f"  {pid} ({pdef['policy_type']}, scope={pdef['scope_level']}, udf={pdef['udf']})")

# COMMAND ----------

# DBTITLE 1,Collect Bindings from Securables
# Walk securables.yaml at all 3 levels and collect (scope, target, policy_id)
bindings = []

# Catalog-level
for catalog in securables_config.get("catalogs", []):
    for policy_id in catalog.get("policy_bindings", []):
        bindings.append(("CATALOG", catalog["catalog_id"], policy_id))

# Schema-level
for schema in securables_config.get("schemas", []):
    schema_fqn = f"{schema['catalog']}.{schema['schema_id']}"
    for policy_id in schema.get("policy_bindings", []):
        bindings.append(("SCHEMA", schema_fqn, policy_id))

# Table-level
for table in securables_config.get("tables", []):
    table_fqn = f"{table['catalog']}.{table['schema']}.{table['table_id']}"
    for policy_id in table.get("policy_bindings", []):
        bindings.append(("TABLE", table_fqn, policy_id))

print(f"Total policy bindings: {len(bindings)}")
print("=" * 60)
for scope_type, fqn, pid in bindings:
    print(f"  {scope_type:8s} {fqn:40s} <- {pid}")

# COMMAND ----------

# DBTITLE 1,SQL Builder Function
def build_create_policy_sql(policy_id, policy_def, scope_type, securable_fqn):
    """Generate CREATE OR REPLACE POLICY SQL from a policies.yaml definition."""
    policy_type = policy_def["policy_type"]
    udf_name = f"{udf_prefix}.{policy_def['udf']}"
    description = policy_def.get("description", "").replace("'", "''")

    # Principals (TO / EXCEPT)
    to_principals = policy_def.get("principals", {}).get("to", [])
    except_principals = policy_def.get("principals", {}).get("except", [])
    to_clause = ", ".join(to_principals)
    except_clause = ", ".join(p for p in except_principals if "{" not in p)

    # Conditions
    when_conditions = policy_def.get("when", [])
    match_columns = policy_def.get("match_columns", [])
    using_columns = policy_def.get("using_columns", [])

    # Assemble SQL
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

    if when_conditions:
        lines.append(f"WHEN {' AND '.join(when_conditions)}")

    # MATCH COLUMNS: only emit if explicit tag-based conditions are defined
    # (ABAC only supports has_tag/has_tag_value — no column-by-name matching)
    if match_columns:
        parts = [f"{mc['condition']} AS {mc['alias']}" if mc.get('alias') else mc['condition'] for mc in match_columns]
        lines.append(f"MATCH COLUMNS {', '.join(parts)}")
    elif policy_type == "row_filter" and using_columns:
        # Row filters need MATCH COLUMNS to define aliases for USING COLUMNS.
        # Without tag-based match_columns in the policy config, we cannot proceed.
        raise ValueError(
            f"Policy '{policy_id}': row filter references using_columns {using_columns} "
            f"but has no match_columns with has_tag() conditions. "
            f"ABAC requires tag-based MATCH COLUMNS — tag the target columns and add match_columns to policies.yaml."
        )

    if policy_type == "column_mask" and policy_def.get("on_column"):
        lines.append(f"ON COLUMN {policy_def['on_column']}")

    # USING COLUMNS: for column masks, skip if it only references the ON COLUMN alias
    # (ON COLUMN already passes the value as the implicit first UDF argument)
    if using_columns:
        on_col = policy_def.get("on_column", "")
        if policy_type == "column_mask" and using_columns == [on_col]:
            pass  # ON COLUMN already provides the single UDF argument
        else:
            lines.append(f"USING COLUMNS ({', '.join(using_columns)})")

    return "\n".join(lines)

print("\u2713 build_create_policy_sql() defined")

# COMMAND ----------

# DBTITLE 1,Dry Run — Preview Generated SQL
# Preview the SQL that will be executed (no changes made)
print("DRY RUN: Generated SQL statements")
print("=" * 60)

for scope_type, securable_fqn, policy_id in bindings:
    if policy_id not in policy_lookup:
        print(f"\n  \u23ed {policy_id} -- not found in policies.yaml, will skip")
        continue

    policy_def = policy_lookup[policy_id]
    try:
        sql = build_create_policy_sql(policy_id, policy_def, scope_type, securable_fqn)
    except Exception as e:
        print(f"\n  \u2717 {policy_id} -- {str(e)[:200]}")
        continue

    print(f"\n  \u25b6 {policy_id} ({policy_def['policy_type']}) -> {scope_type} {securable_fqn}")
    print(f"  {'-' * 56}")
    for line in sql.split("\n"):
        print(f"    {line}")
    print()

# COMMAND ----------

# DBTITLE 1,Execute — Apply All Policies
deployed = []
failed = []
skipped = []

print("Creating ABAC policies...")
print("=" * 60)

for scope_type, securable_fqn, policy_id in bindings:
    if policy_id not in policy_lookup:
        skipped.append((policy_id, "not in policies.yaml"))
        print(f"  \u23ed {policy_id} -- skipped (not in policies.yaml)")
        continue

    policy_def = policy_lookup[policy_id]

    try:
        sql = build_create_policy_sql(policy_id, policy_def, scope_type, securable_fqn)
        spark.sql(sql)
        deployed.append(policy_id)
        print(f"  \u2713 {policy_id} -> {scope_type} {securable_fqn}")
    except Exception as e:
        error_msg = str(e)[:200]
        failed.append((policy_id, error_msg))
        print(f"  \u2717 {policy_id}: {error_msg}")

print(f"\n{'=' * 60}")
print(f"Deployed: {len(deployed)} | Skipped: {len(skipped)} | Failed: {len(failed)}")

# COMMAND ----------

# DBTITLE 1,Verify — SHOW POLICIES
print("Verification:")
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

if failed:
    print(f"\n\u2717 Failures:")
    for pid, err in failed:
        print(f"    - {pid}: {err}")
    raise Exception(f"POLICY DEPLOYMENT HAD {len(failed)} FAILURE(S)")
else:
    print(f"\n\u2713 All {len(deployed)} ABAC policies created successfully")