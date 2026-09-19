# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 03: Deploy Masking UDFs
"""
Step 03: Deploy Policy UDFs (Row Filters & Column Masks)

Reads UDF definitions from policies.yaml `udf_registry` section and deploys
them as SQL functions in Unity Catalog.

Deploys both:
- Row filter functions (return BOOLEAN)
- Column mask functions (return masked value)

No UDF logic is hardcoded — policies.yml is the single source of truth.

NOTE: policies.yml is read directly with yaml.safe_load. config_loader's
ABACConfigLoader is deliberately NOT used here - it hardcodes 'policies.yaml',
globs '*.yaml', and expects a configs/securables/ tree that does not exist in
this bundle, so .load() raises FileNotFoundError. UDF deployment only needs the
udf_registry section, so the loader buys nothing.
"""
import sys
import os
import yaml

dbutils.widgets.text("project_root", "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac", "Project Root")
dbutils.widgets.text("policies_path", "", "Policies Path (defaults to {project_root}/configs/policies.yml)")
dbutils.widgets.text("dry_run", "false", "Dry Run - print SQL, deploy nothing (true/false)")
dbutils.widgets.text("exit_on_complete", "false", "Call notebook.exit() at the end")

project_root = dbutils.widgets.get("project_root") or "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac"
policies_path = dbutils.widgets.get("policies_path") or f"{project_root}/configs/policies.yml"
dry_run = dbutils.widgets.get("dry_run").lower() == "true"
exit_on_complete = dbutils.widgets.get("exit_on_complete").lower() == "true"

sys.path.insert(0, f"{project_root}/src")

if not os.path.exists(policies_path):
    raise FileNotFoundError(f"policies file not found: {policies_path}")

print(f"Project root: {project_root}")
print(f"Policies:     {policies_path}")
print(f"Dry run:      {dry_run}")
print(f"Exit on complete: {exit_on_complete}")

# COMMAND ----------

# DBTITLE 1,Load UDF Registry from policies.yml
# Load policies.yml and extract the UDF registry
with open(policies_path, "r") as f:
    policies_doc = yaml.safe_load(f) or {}

if "udf_registry" not in policies_doc:
    raise KeyError(f"'udf_registry' section missing from {policies_path}")

udf_registry = policies_doc["udf_registry"]
target_catalog = udf_registry["target_catalog"]
target_schema = udf_registry["target_schema"]
fqn_prefix = f"{target_catalog}.{target_schema}"

row_filters = udf_registry.get("row_filters", []) or []
column_masks = udf_registry.get("column_masks", []) or []

# Tag each entry with its kind up front, so the deploy loop never has to infer
# type via `udf_def in row_filters` (a dict-equality scan that misidentifies
# any two entries with identical contents).
all_udfs = ([("ROW FILTER", u) for u in row_filters]
            + [("COL MASK", u) for u in column_masks])

# Fail fast on a malformed registry instead of part-way through deployment
REQUIRED_KEYS = {"function_id", "returns", "body"}
for kind, u in all_udfs:
    missing = REQUIRED_KEYS - set(u or {})
    if missing:
        raise KeyError(
            f"[{kind}] udf_registry entry "
            f"{(u or {}).get('function_id', '<no function_id>')} "
            f"missing required keys: {sorted(missing)}"
        )

print(f"Target schema: {fqn_prefix}")
print(f"Row filters:   {len(row_filters)} ({', '.join(f['function_id'] for f in row_filters)})")
print(f"Column masks:  {len(column_masks)} ({', '.join(f['function_id'] for f in column_masks)})")
print(f"Total UDFs:    {len(all_udfs)}")

# COMMAND ----------

# DBTITLE 1,Ensure target catalog and schema exist
# Create governance catalog/schema if they don't exist
if dry_run:
    print(f"DRY RUN - would ensure catalog {target_catalog} and schema {fqn_prefix} exist")
else:
    spark.sql(f"CREATE CATALOG IF NOT EXISTS {target_catalog}")
    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {fqn_prefix}")
    print(f"\u2713 Governance schema ready: {fqn_prefix}")

# COMMAND ----------

# DBTITLE 1,Deploy all UDFs from registry
def build_udf_sql(udf_def, fqn_prefix):
    """Generate CREATE OR REPLACE FUNCTION SQL from a udf_registry entry."""
    function_id = udf_def["function_id"]
    description = udf_def.get("description", "")
    parameters = udf_def.get("parameters", []) or []
    returns = udf_def["returns"]
    body = udf_def["body"].rstrip()

    # Build parameter list
    param_list = ", ".join(f"{p['name']} {p['type']}" for p in parameters)

    # Escape single quotes in description for SQL COMMENT
    safe_desc = description.replace("'", "''")

    return f"""CREATE OR REPLACE FUNCTION {fqn_prefix}.{function_id}({param_list})
RETURNS {returns}
COMMENT '{safe_desc}'
{body}"""


# Deploy all UDFs
deployed = []
failed = []

print("DRY RUN - generated SQL (nothing executed):" if dry_run else "Deploying UDFs...")
print("=" * 60)

for udf_type, udf_def in all_udfs:
    function_id = udf_def["function_id"]
    sql = build_udf_sql(udf_def, fqn_prefix)

    if dry_run:
        print(f"\n-- [{udf_type}] {fqn_prefix}.{function_id}")
        print(sql)
        continue

    try:
        spark.sql(sql)
        deployed.append(function_id)
        print(f"  \u2713 [{udf_type}] {fqn_prefix}.{function_id}")
    except Exception as e:
        failed.append((function_id, str(e)[:200]))
        print(f"  \u2717 [{udf_type}] {fqn_prefix}.{function_id}: {str(e)[:200]}")

print(f"\n{'=' * 60}")
if dry_run:
    print(f"DRY RUN - {len(all_udfs)} UDFs would be deployed to {fqn_prefix}")
else:
    print(f"Deployed: {len(deployed)} | Failed: {len(failed)}")

# COMMAND ----------

# DBTITLE 1,Verify deployment against information_schema
# Verify UDFs exist in information_schema
if dry_run:
    print("DRY RUN - skipping verification (nothing was deployed)")
    dbutils.notebook.exit(f"dry_run=True, planned={len(all_udfs)}")

print("\nVerification: Functions in governance schema")
print("=" * 60)

# NOTE: information_schema.routines has NO 'function_name' column - it is
# 'routine_name'. The previous query selected function_name, so it always threw
# and the bare except swallowed the error, letting this notebook report success
# while verifying nothing. Verification failures are now real failures.
expected = {u["function_id"] for _, u in all_udfs}
found = set()
verification_error = None

try:
    funcs_df = spark.sql(f"""
        SELECT routine_name, data_type, comment
        FROM {target_catalog}.information_schema.routines
        WHERE routine_schema = '{target_schema}'
        ORDER BY routine_name
    """)
    for row in funcs_df.collect():
        found.add(row.routine_name)
        marker = "\u2713" if row.routine_name in expected else " "
        print(f"  {marker} {row.routine_name} -> {row.data_type}")
except Exception as e:
    verification_error = str(e)
    print(f"  \u2717 verification query failed: {e}")

missing = expected - found

# Summary
if failed:
    print(f"\n\u2717 {len(failed)} UDFs failed deployment:")
    for fname, err in failed:
        print(f"    - {fname}: {err}")
    raise Exception(f"UDF DEPLOYMENT HAD {len(failed)} FAILURE(S)")

if verification_error:
    raise Exception(f"UDF VERIFICATION QUERY FAILED: {verification_error}")

if missing:
    print(f"\n\u2717 Expected UDFs absent from {fqn_prefix}: {sorted(missing)}")
    raise Exception(f"UDF VERIFICATION FAILED: {sorted(missing)} not found in information_schema")

print(f"\n\u2713 All {len(deployed)} UDFs deployed and verified in {fqn_prefix}")

summary = f"deployed={len(deployed)}, failed={len(failed)}, verified={len(expected & found)}"
print("\n" + "=" * 60)
print(f"SUMMARY: {summary}")