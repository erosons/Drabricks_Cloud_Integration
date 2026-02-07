# Databricks notebook source
# MAGIC %md
# MAGIC # Delta Live Tables Pipeline - Bronze Layer
# MAGIC 
# MAGIC This notebook defines DLT tables for the bronze (raw) layer.
# MAGIC 
# MAGIC **Note:** Uncomment the `pipelines` section in databricks.yml to enable DLT.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# =============================================================================
# Configuration
# =============================================================================

# Source configuration - update for your data source
SOURCE_PATH = "/mnt/raw/events/"  # Or use cloud storage path
SOURCE_FORMAT = "json"

# =============================================================================
# Bronze Tables
# =============================================================================

@dlt.table(
    name="bronze_raw_events",
    comment="Raw events ingested from source system",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.optimizeWrite": "true"
    }
)
def bronze_raw_events():
    """
    Ingest raw events with metadata.
    Uses Auto Loader for incremental ingestion.
    """
    return (
        spark.readStream
        .format("cloudFiles")
        .option("cloudFiles.format", SOURCE_FORMAT)
        .option("cloudFiles.inferColumnTypes", "true")
        .option("cloudFiles.schemaLocation", f"{SOURCE_PATH}/_schema")
        .load(SOURCE_PATH)
        .withColumn("_ingestion_timestamp", F.current_timestamp())
        .withColumn("_source_file", F.input_file_name())
    )


@dlt.table(
    name="bronze_raw_events_quarantine",
    comment="Quarantined records that failed initial validation",
    table_properties={
        "quality": "bronze"
    }
)
@dlt.expect_all_or_drop({
    "valid_id": "id IS NOT NULL",
    "valid_timestamp": "event_timestamp IS NOT NULL"
})
def bronze_raw_events_quarantine():
    """
    Quarantine records that fail basic validation.
    These can be reviewed and reprocessed.
    """
    return dlt.read_stream("bronze_raw_events")


# =============================================================================
# Data Quality Expectations
# =============================================================================

# Define reusable expectations
BRONZE_EXPECTATIONS = {
    "valid_record": "id IS NOT NULL AND event_timestamp IS NOT NULL",
    "valid_payload": "payload IS NOT NULL"
}
