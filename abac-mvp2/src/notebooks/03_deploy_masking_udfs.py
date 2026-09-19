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

No UDF logic is hardcoded — policies.yaml is the single source of truth.
Uses the MVP2 config loader for consistency with multi-file architecture.
"""
import sys
import os

dbutils.widgets.text("config_path", "", "Config Directory")
dbutils.widgets.text("project_root", "", "Project Root")

config_path = dbutils.widgets.get("config_path") or "/Workspace/abac-mvp2/configs" or "/Workspace/abac-mvp2/configs"
project_root = dbutils.widgets.get("project_root") or "/Workspace/abac-mvp2"

sys.path.insert(0, f"{project_root}/src")
from config_loader import ABACConfigLoader

print(f"Config path: {config_path}")

# COMMAND ----------

# DBTITLE 1,Load UDF Registry from policies.yaml
# Load the governance manifest
loader = ABACConfigLoader(config_path)
manifest = loader.load()

# Extract UDF registry
udf_registry = manifest.policies["udf_registry"]
target_catalog = udf_registry["target_catalog"]
target_schema = udf_registry["target_schema"]
fqn_prefix = f"{target_catalog}.{target_schema}"

row_filters = udf_registry.get("row_filters", [])
column_masks = udf_registry.get("column_masks", [])
all_udfs = row_filters + column_masks

print(f"Target schema: {fqn_prefix}")
print(f"Row filters:   {len(row_filters)} ({', '.join(f['function_id'] for f in row_filters)})")
print(f"Column masks:  {len(column_masks)} ({', '.join(f['function_id'] for f in column_masks)})")
print(f"Total UDFs:    {len(all_udfs)}")

# COMMAND ----------

# DBTITLE 1,Ensure target catalog and schema exist
# Create governance schema if it doesn't exist
spark.sql(f"CREATE CATALOG IF NOT EXISTS {target_catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {fqn_prefix}")
print(f"\u2713 Governance schema ready: {fqn_prefix}")

# COMMAND ----------

# DBTITLE 1,Deploy all UDFs from registry
def deploy_udf(udf_def, fqn_prefix):
    """Generate and execute CREATE OR REPLACE FUNCTION from a udf_registry entry."""
    function_id = udf_def["function_id"]
    description = udf_def.get("description", "")
    parameters = udf_def.get("parameters", [])
    returns = udf_def["returns"]
    body = udf_def["body"].rstrip()

    # Build parameter list
    param_list = ", ".join(f"{p['name']} {p['type']}" for p in parameters)

    # Escape single quotes in description for SQL COMMENT
    safe_desc = description.replace("'", "''")

    sql = f"""CREATE OR REPLACE FUNCTION {fqn_prefix}.{function_id}({param_list})
RETURNS {returns}
COMMENT '{safe_desc}'
{body}"""

    spark.sql(sql)
    return sql


# Deploy all UDFs
deployed = []
failed = []

print("Deploying UDFs...")
print("=" * 60)

for udf_def in all_udfs:
    function_id = udf_def["function_id"]
    udf_type = "ROW FILTER" if udf_def in row_filters else "COL MASK"
    try:
        deploy_udf(udf_def, fqn_prefix)
        deployed.append(function_id)
        print(f"  \u2713 [{udf_type}] {fqn_prefix}.{function_id}")
    except Exception as e:
        failed.append((function_id, str(e)[:200]))
        print(f"  \u2717 [{udf_type}] {fqn_prefix}.{function_id}: {str(e)[:200]}")

print(f"\n{'=' * 60}")
print(f"Deployed: {len(deployed)} | Failed: {len(failed)}")

# COMMAND ----------

# DBTITLE 1,Verify deployment against information_schema
# Verify UDFs exist in information_schema
print("\nVerification: Functions in governance schema")
print("=" * 60)

try:
    funcs_df = spark.sql(f"""
        SELECT function_name, data_type, comment
        FROM {target_catalog}.information_schema.routines
        WHERE routine_schema = '{target_schema}'
        ORDER BY function_name
    """)
    for row in funcs_df.collect():
        print(f"  \u2713 {row.function_name} -> {row.data_type}")
except Exception as e:
    print(f"  (verification query failed: {e})")

# Summary
if failed:
    print(f"\n\u2717 {len(failed)} UDFs failed deployment:")
    for fname, err in failed:
        print(f"    - {fname}: {err}")
    raise Exception(f"UDF DEPLOYMENT HAD {len(failed)} FAILURE(S)")

print(f"\n\u2713 All {len(deployed)} UDFs deployed successfully to {fqn_prefix}")
dbutils.notebook.exit(f"deployed={len(deployed)}, failed={len(failed)}")