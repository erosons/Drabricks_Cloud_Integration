# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze Layer - Raw Data Ingestion
# MAGIC 
# MAGIC This notebook ingests raw data from source systems into the bronze layer.
# MAGIC 
# MAGIC **Layer:** Bronze (Raw)  
# MAGIC **Pattern:** Append-only with metadata  
# MAGIC **Data Quality:** Minimal - preserve source fidelity

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

# Widget parameters (passed from job configuration)
dbutils.widgets.text("catalog", "dev_catalog", "Target Catalog")
dbutils.widgets.text("schema", "default", "Target Schema")
dbutils.widgets.text("source_path", "", "Source Data Path (optional)")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
source_path = dbutils.widgets.get("source_path")

print(f"Catalog: {catalog}")
print(f"Schema: {schema}")
print(f"Source Path: {source_path}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import *
from datetime import datetime

# Set catalog and schema context
spark.sql(f"USE CATALOG {catalog}")
spark.sql(f"USE SCHEMA {schema}")

# Ingestion metadata
ingestion_timestamp = datetime.now()
ingestion_id = f"ingest_{ingestion_timestamp.strftime('%Y%m%d_%H%M%S')}"

print(f"Ingestion ID: {ingestion_id}")
print(f"Ingestion Timestamp: {ingestion_timestamp}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Define Source Schema
# MAGIC 
# MAGIC Define the expected schema for your source data. Adjust based on your actual source.

# COMMAND ----------

# Example schema - customize for your data source
source_schema = StructType([
    StructField("id", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("event_timestamp", TimestampType(), True),
    StructField("payload", StringType(), True),
    StructField("source_system", StringType(), True)
])

# COMMAND ----------

# MAGIC %md
# MAGIC ## Ingest Data
# MAGIC 
# MAGIC Replace this section with your actual data ingestion logic.

# COMMAND ----------

def add_ingestion_metadata(df):
    """Add standard bronze layer metadata columns."""
    return df \
        .withColumn("_ingestion_timestamp", F.lit(ingestion_timestamp)) \
        .withColumn("_ingestion_id", F.lit(ingestion_id)) \
        .withColumn("_source_file", F.input_file_name()) \
        .withColumn("_processing_timestamp", F.current_timestamp())

# COMMAND ----------

# Example: Read from a source location
# Uncomment and modify based on your source type

# Option 1: Read from cloud storage (CSV)
# raw_df = spark.read \
#     .format("csv") \
#     .option("header", "true") \
#     .schema(source_schema) \
#     .load(source_path)

# Option 2: Read from cloud storage (JSON)
# raw_df = spark.read \
#     .format("json") \
#     .schema(source_schema) \
#     .load(source_path)

# Option 3: Read from cloud storage (Parquet)
# raw_df = spark.read \
#     .format("parquet") \
#     .load(source_path)

# Option 4: Read using Auto Loader (recommended for streaming ingestion)
# raw_df = spark.readStream \
#     .format("cloudFiles") \
#     .option("cloudFiles.format", "json") \
#     .option("cloudFiles.schemaLocation", f"/mnt/checkpoints/{schema}/bronze_schema") \
#     .load(source_path)

# For template demonstration - create sample data
sample_data = [
    ("001", "click", datetime.now(), '{"page": "home"}', "web"),
    ("002", "purchase", datetime.now(), '{"amount": 99.99}', "mobile"),
    ("003", "view", datetime.now(), '{"item": "product_a"}', "web"),
]

raw_df = spark.createDataFrame(sample_data, source_schema)
print(f"Raw records read: {raw_df.count()}")

# COMMAND ----------

# Add metadata columns
bronze_df = add_ingestion_metadata(raw_df)

# Display sample
display(bronze_df.limit(10))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write to Bronze Table

# COMMAND ----------

bronze_table = "bronze_events"

# Write to Delta table (append mode for bronze)
bronze_df.write \
    .format("delta") \
    .mode("append") \
    .option("mergeSchema", "true") \
    .saveAsTable(bronze_table)

print(f"Data written to {catalog}.{schema}.{bronze_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation

# COMMAND ----------

# Record count validation
record_count = spark.table(bronze_table).count()
ingested_count = bronze_df.count()

print(f"Total records in bronze table: {record_count}")
print(f"Records ingested this run: {ingested_count}")

# Basic validation
assert ingested_count > 0, "No records were ingested!"

# COMMAND ----------

# MAGIC %md
# MAGIC ## Output Metrics

# COMMAND ----------

# Return metrics for job tracking
dbutils.notebook.exit({
    "status": "SUCCESS",
    "ingestion_id": ingestion_id,
    "records_ingested": ingested_count,
    "target_table": f"{catalog}.{schema}.{bronze_table}"
})
