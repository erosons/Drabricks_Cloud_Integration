# Databricks notebook source
# MAGIC %md
# MAGIC # Step 3: Deploy Policy UDFs
# MAGIC Reads UDF definitions from `policies.yaml` `udf_registry` section and deploys
# MAGIC them as SQL functions in Unity Catalog.
# MAGIC
# MAGIC Deploys both:
# MAGIC - **Row filter functions** (return BOOLEAN)
# MAGIC - **Column mask functions** (return masked value)
# MAGIC
# MAGIC No UDF logic is hardcoded here — policies.yaml is the single source of truth.

# COMMAND ----------

import yaml
import os

dbutils.widgets.text("config_path", "/Workspace/Users/samson.eromonsei@databricks.com/abac/configs", "Config Directory")
config_path = dbutils.widgets.get("config_path")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Load UDF definitions from policies.yaml

# COMMAND ----------

with open(os.path.join(config_path, "policies.yaml"), "r") as f:
    policies_config = yaml.safe_load(f)

udf_registry = policies_config["udf_registry"]
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

# MAGIC %md
# MAGIC ## 2. Ensure target catalog and schema exist

# COMMAND ----------

spark.sql(f"CREATE CATALOG IF NOT EXISTS {target_catalog}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {fqn_prefix}")
print(f"\u2713 Governance schema ready: {fqn_prefix}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Deploy all UDFs from registry

# COMMAND ----------

def deploy_udf(udf_def, fqn_prefix):
    """Generate and execute CREATE OR REPLACE FUNCTION from a udf_registry entry."""
    function_id = udf_def["function_id"]
    description = udf_def.get("description", "")
    parameters = udf_def.get("parameters", [])
    returns = udf_def["returns"]
    body = udf_def["body"].rstrip()

    # Build parameter list: (param1 TYPE1, param2 TYPE2, ...)
    param_list = ", ".join(f"{p['name']} {p['type']}" for p in parameters)

    # Escape single quotes in description for SQL COMMENT
    safe_desc = description.replace("'", "''")

    sql = f"""CREATE OR REPLACE FUNCTION {fqn_prefix}.{function_id}({param_list})
RETURNS {returns}
COMMENT '{safe_desc}'
{body}"""

    spark.sql(sql)
    return sql

# COMMAND ----------

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
        failed.append((function_id, str(e)[:100]))
        print(f"  \u2717 [{udf_type}] {fqn_prefix}.{function_id}: {str(e)[:100]}")

print(f"\n{'=' * 60}")
print(f"Deployed: {len(deployed)} | Failed: {len(failed)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Verify deployment against information_schema

# COMMAND ----------

expected_udfs = set(udf_def["function_id"] for udf_def in all_udfs)
expected_list = ", ".join(f"'{name}'" for name in sorted(expected_udfs))

verify_df = spark.sql(f"""
    SELECT routine_name, data_type, comment
    FROM system.information_schema.routines
    WHERE routine_catalog = '{target_catalog}'
      AND routine_schema = '{target_schema}'
      AND routine_name IN ({expected_list})
    ORDER BY routine_name
""")

print("Deployed UDFs in UC:")
print("=" * 60)
display(verify_df)

actual_udfs = set(row['routine_name'] for row in verify_df.collect())
missing = expected_udfs - actual_udfs

if missing:
    print(f"\n\u26a0 Missing from UC: {sorted(missing)}")
    if failed:
        print(f"\n\u2717 Failures:")
        for name, err in failed:
            print(f"    - {name}: {err}")
    raise Exception(f"VALIDATION FAILED: {len(missing)} UDF(s) not found in UC: {sorted(missing)}")
else:
    print(f"\n\u2713 All {len(expected_udfs)} UDFs verified in information_schema")