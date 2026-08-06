# Databricks notebook source
# MAGIC %md
# MAGIC # Teardown: Remove Test Environment
# MAGIC Cleans up all test artifacts for a fresh re-run.
# MAGIC **Use with caution** - this removes policies, tags, UDFs, and test data.

# COMMAND ----------

dbutils.widgets.text("governance_catalog", "governance", "Governance Catalog")
dbutils.widgets.text("governance_schema", "policy_functions", "Governance Schema")
dbutils.widgets.text("target_catalog", "general_use", "Target Catalog")
dbutils.widgets.text("target_schema", "customer", "Target Schema")

gov_catalog = dbutils.widgets.get("governance_catalog")
gov_schema = dbutils.widgets.get("governance_schema")
target_catalog = dbutils.widgets.get("target_catalog")
target_schema = dbutils.widgets.get("target_schema")

print(f"TEARDOWN TARGET:")
print(f"  Policies on: {target_catalog}.{target_schema}")
print(f"  UDFs in:     {gov_catalog}.{gov_schema}")
print(f"  Test table:  {target_catalog}.{target_schema}.customer_profile")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 1: Drop ABAC Policies

# COMMAND ----------

policies_to_drop = [
    ("mask_email_policy", f"SCHEMA {target_catalog}.{target_schema}"),
    ("mask_phone_policy", f"SCHEMA {target_catalog}.{target_schema}"),
    ("mask_dob_policy", f"SCHEMA {target_catalog}.{target_schema}"),
]

print("Dropping ABAC policies...")
for policy_name, scope in policies_to_drop:
    try:
        spark.sql(f"DROP POLICY {policy_name} ON {scope}")
        print(f"  \u2713 Dropped: {policy_name}")
    except Exception as e:
        if "POLICY_NOT_FOUND" in str(e) or "not found" in str(e).lower():
            print(f"  - Skipped (not found): {policy_name}")
        else:
            print(f"  \u2717 Error: {policy_name}: {str(e)[:60]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 2: Remove governed tags from columns

# COMMAND ----------

table_fqn = f"{target_catalog}.{target_schema}.customer_profile"

tags_to_remove = [
    ("email", "class.email_address"),
    ("phone_number", "class.phone_number"),
    ("date_of_birth", "class.date_of_birth"),
]

print("Removing governed tags...")
for col_name, tag_key in tags_to_remove:
    try:
        spark.sql(f"UNSET TAG ON COLUMN {table_fqn}.{col_name} `{tag_key}`;")
        print(f"  \u2713 Removed: {table_fqn}.{col_name} <- {tag_key}")
    except Exception as e:
        if "not found" in str(e).lower() or "does not exist" in str(e).lower():
            print(f"  - Skipped (not found): {col_name} <- {tag_key}")
        else:
            print(f"  \u2717 Error: {col_name}: {str(e)[:60]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 3: Drop masking UDFs

# COMMAND ----------

udfs_to_drop = ["mask_email", "mask_phone", "mask_dob"]

print("Dropping masking UDFs...")
for udf_name in udfs_to_drop:
    try:
        spark.sql(f"DROP FUNCTION IF EXISTS {gov_catalog}.{gov_schema}.{udf_name}")
        print(f"  \u2713 Dropped: {gov_catalog}.{gov_schema}.{udf_name}")
    except Exception as e:
        print(f"  \u2717 Error: {udf_name}: {str(e)[:60]}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Step 4: Drop test table

# COMMAND ----------

try:
    spark.sql(f"DROP TABLE IF EXISTS {table_fqn}")
    print(f"\u2713 Dropped test table: {table_fqn}")
except Exception as e:
    print(f"\u2717 Error dropping table: {str(e)[:80]}")

# COMMAND ----------

print(f"""
{'='*60}
TEARDOWN COMPLETE
{'='*60}
Removed:
  - 3 ABAC column mask policies
  - 3 governed tag assignments
  - 3 masking UDFs
  - 1 test table

Environment is clean for a fresh deployment.
Run 'databricks bundle run governance_deploy' to redeploy.
{'='*60}
""")
