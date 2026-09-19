# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 00: Load ABAC Mapping Table from Onboarding JSON
"""
Step 00: Load ABAC Mapping Table

Reads the SDP-META onboarding JSON from UC Volume and extracts
bronze_abac_governance and silver_abac_governance paths into a
dedicated mapping table for ABAC framework consumption.

This bridges the gap where the SDP-META framework doesn't yet
persist ABAC paths in the dataflowspec tables.

Output:
  - Table: {catalog}.{sdp_meta_schema}.abac_dataflowspec_mapping
  - Schema: dataFlowId, bronze_abac_governance, silver_abac_governance
"""

import json
from pyspark.sql import SparkSession
from pyspark.sql.types import StructType, StructField, StringType

# Widgets for configuration
dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("uc_volume_path", "/Volumes/general_use/platform_admin/sdp_meta_files", "UC Volume Path")
dbutils.widgets.text("onboarding_json_path", "", "Onboarding JSON Path (optional - defaults to {uc_volume_path}/conf/onboarding_all_usecases.json)")

catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
uc_volume_path = dbutils.widgets.get("uc_volume_path")
onboarding_json_path = dbutils.widgets.get("onboarding_json_path") or f"{uc_volume_path}/conf/onboarding_all_usecases.json"

print(f"Loading ABAC mapping from: {onboarding_json_path}")

# COMMAND ----------

# DBTITLE 1,Read Onboarding JSON and Extract ABAC Paths
# Load onboarding JSON
with open(onboarding_json_path, "r") as f:
    onboarding_data = json.load(f)

print(f"Loaded {len(onboarding_data)} use case(s) from onboarding JSON")

# Extract ABAC mapping
abac_mappings = []
for use_case in onboarding_data:
    data_flow_id = use_case.get("data_flow_id")
    bronze_abac = use_case.get("bronze_abac_governance")
    silver_abac = use_case.get("silver_abac_governance")

    # Only include if at least one ABAC path is defined
    if bronze_abac or silver_abac:
        abac_mappings.append({
            "dataFlowId": data_flow_id,
            "bronze_abac_governance": bronze_abac,
            "silver_abac_governance": silver_abac,
            "data_flow_group": use_case.get("data_flow_group"),
            "source_system": use_case.get("source_system"),
        })
        print(f"  Flow {data_flow_id}: bronze={bronze_abac}, silver={silver_abac}")

print(f"\nFound {len(abac_mappings)} flow(s) with ABAC governance")

# COMMAND ----------

# DBTITLE 1,Create ABAC Mapping Table
if abac_mappings:
    schema = StructType([
        StructField("dataFlowId", StringType(), False),
        StructField("bronze_abac_governance", StringType(), True),
        StructField("silver_abac_governance", StringType(), True),
        StructField("data_flow_group", StringType(), True),
        StructField("source_system", StringType(), True),
    ])

    df = spark.createDataFrame(abac_mappings, schema)

    # Write to Delta table
    target_table = f"{catalog}.{sdp_meta_schema}.abac_dataflowspec_mapping"

    df.write \
        .format("delta") \
        .mode("overwrite") \
        .option("overwriteSchema", "true") \
        .saveAsTable(target_table)

    print(f"\n✓ Created ABAC mapping table: {target_table}")
    print(f"  Rows: {df.count()}")

    # Display sample
    display(df)
else:
    print("\n⚠ No ABAC governance paths found in onboarding JSON")

# COMMAND ----------

# DBTITLE 1,Validate Mapping Table
# Query the table to confirm
target_table = f"{catalog}.{sdp_meta_schema}.abac_dataflowspec_mapping"
result_df = spark.sql(f"SELECT * FROM {target_table}")

print(f"\n✓ ABAC Mapping Table validated: {target_table}")
print(f"  Total rows: {result_df.count()}")
print("\nSample:")
display(result_df)