# Databricks notebook source
# MAGIC %md
# MAGIC # Silver Layer - Data Transformation
# MAGIC 
# MAGIC This notebook transforms bronze data into cleaned, conformed silver layer tables.
# MAGIC 
# MAGIC **Layer:** Silver (Cleansed)  
# MAGIC **Pattern:** Merge/Upsert with SCD Type 1 or 2  
# MAGIC **Data Quality:** Validated, deduplicated, standardized

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

dbutils.widgets.text("catalog", "dev_catalog", "Target Catalog")
dbutils.widgets.text("schema", "default", "Target Schema")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

print(f"Catalog: {catalog}")
print(f"Schema: {schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window
from delta.tables import DeltaTable
from datetime import datetime

spark.sql(f"USE CATALOG {catalog}")
spark.sql(f"USE SCHEMA {schema}")

processing_timestamp = datetime.now()
print(f"Processing Timestamp: {processing_timestamp}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read Bronze Data

# COMMAND ----------

bronze_table = "bronze_events"

# Read new/unprocessed records from bronze
# Option 1: Read all (for full refresh)
bronze_df = spark.table(bronze_table)

# Option 2: Incremental - read only new records (uncomment to use)
# last_processed = spark.sql(f"""
#     SELECT MAX(_processing_timestamp) as max_ts 
#     FROM silver_events
# """).collect()[0]["max_ts"]
# 
# bronze_df = spark.table(bronze_table) \
#     .filter(F.col("_ingestion_timestamp") > last_processed)

print(f"Bronze records to process: {bronze_df.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Data Quality & Cleansing

# COMMAND ----------

def apply_data_quality_rules(df):
    """Apply standard data quality rules for silver layer."""
    
    return df \
        .filter(F.col("id").isNotNull()) \
        .filter(F.col("event_type").isNotNull()) \
        .withColumn("id", F.trim(F.col("id"))) \
        .withColumn("event_type", F.lower(F.trim(F.col("event_type")))) \
        .withColumn("source_system", F.upper(F.trim(F.coalesce(F.col("source_system"), F.lit("UNKNOWN")))))

# COMMAND ----------

def deduplicate_records(df, key_columns, order_column):
    """Remove duplicates keeping the latest record."""
    
    window_spec = Window \
        .partitionBy(*key_columns) \
        .orderBy(F.col(order_column).desc())
    
    return df \
        .withColumn("_row_num", F.row_number().over(window_spec)) \
        .filter(F.col("_row_num") == 1) \
        .drop("_row_num")

# COMMAND ----------

def parse_payload(df):
    """Parse JSON payload into structured columns."""
    
    # Define expected payload schema
    payload_schema = "page STRING, amount DOUBLE, item STRING"
    
    return df \
        .withColumn("payload_parsed", F.from_json(F.col("payload"), payload_schema)) \
        .withColumn("page", F.col("payload_parsed.page")) \
        .withColumn("amount", F.col("payload_parsed.amount")) \
        .withColumn("item", F.col("payload_parsed.item")) \
        .drop("payload_parsed")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Apply Transformations

# COMMAND ----------

# Apply transformations in sequence
silver_df = bronze_df \
    .transform(apply_data_quality_rules) \
    .transform(lambda df: deduplicate_records(df, ["id"], "_ingestion_timestamp")) \
    .transform(parse_payload)

# Add silver layer metadata
silver_df = silver_df \
    .withColumn("_silver_processed_at", F.lit(processing_timestamp)) \
    .withColumn("_silver_version", F.lit(1))

# Select final columns for silver table
silver_df = silver_df.select(
    "id",
    "event_type",
    "event_timestamp",
    "source_system",
    "page",
    "amount",
    "item",
    "_ingestion_timestamp",
    "_silver_processed_at",
    "_silver_version"
)

print(f"Silver records after transformation: {silver_df.count()}")
display(silver_df.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write to Silver Table (Merge/Upsert)

# COMMAND ----------

silver_table = "silver_events"

# Check if table exists
table_exists = spark.catalog.tableExists(silver_table)

if not table_exists:
    # Initial load - create table
    silver_df.write \
        .format("delta") \
        .mode("overwrite") \
        .option("overwriteSchema", "true") \
        .saveAsTable(silver_table)
    
    print(f"Created new table: {catalog}.{schema}.{silver_table}")
    records_merged = silver_df.count()
    records_inserted = records_merged
    records_updated = 0

else:
    # Incremental load - merge/upsert
    delta_table = DeltaTable.forName(spark, silver_table)
    
    merge_result = delta_table.alias("target") \
        .merge(
            silver_df.alias("source"),
            "target.id = source.id"
        ) \
        .whenMatchedUpdate(set={
            "event_type": "source.event_type",
            "event_timestamp": "source.event_timestamp",
            "source_system": "source.source_system",
            "page": "source.page",
            "amount": "source.amount",
            "item": "source.item",
            "_ingestion_timestamp": "source._ingestion_timestamp",
            "_silver_processed_at": "source._silver_processed_at",
            "_silver_version": "target._silver_version + 1"
        }) \
        .whenNotMatchedInsertAll() \
        .execute()
    
    print(f"Merged data into: {catalog}.{schema}.{silver_table}")
    
    # Get merge metrics
    history = delta_table.history(1).collect()[0]
    metrics = history["operationMetrics"]
    records_inserted = int(metrics.get("numTargetRowsInserted", 0))
    records_updated = int(metrics.get("numTargetRowsUpdated", 0))
    records_merged = records_inserted + records_updated

print(f"Records inserted: {records_inserted}")
print(f"Records updated: {records_updated}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation

# COMMAND ----------

# Count validation
total_silver_records = spark.table(silver_table).count()
print(f"Total records in silver table: {total_silver_records}")

# Null check on key columns
null_check = spark.table(silver_table) \
    .select(
        F.sum(F.when(F.col("id").isNull(), 1).otherwise(0)).alias("null_ids"),
        F.sum(F.when(F.col("event_type").isNull(), 1).otherwise(0)).alias("null_event_types")
    ).collect()[0]

assert null_check["null_ids"] == 0, "Found null IDs in silver table!"
assert null_check["null_event_types"] == 0, "Found null event_types in silver table!"

print("Data quality validation passed!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Output Metrics

# COMMAND ----------

dbutils.notebook.exit({
    "status": "SUCCESS",
    "records_processed": records_merged,
    "records_inserted": records_inserted,
    "records_updated": records_updated,
    "target_table": f"{catalog}.{schema}.{silver_table}"
})
