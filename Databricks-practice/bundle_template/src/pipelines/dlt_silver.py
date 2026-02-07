# Databricks notebook source
# MAGIC %md
# MAGIC # Delta Live Tables Pipeline - Silver Layer
# MAGIC 
# MAGIC This notebook defines DLT tables for the silver (cleansed) layer.

# COMMAND ----------

import dlt
from pyspark.sql import functions as F

# =============================================================================
# Silver Tables
# =============================================================================

@dlt.table(
    name="silver_events",
    comment="Cleansed and validated events",
    table_properties={
        "quality": "silver",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true"
    }
)
@dlt.expect_or_drop("valid_id", "id IS NOT NULL")
@dlt.expect_or_drop("valid_event_type", "event_type IS NOT NULL")
@dlt.expect("valid_amount", "amount IS NULL OR amount >= 0")
def silver_events():
    """
    Transform bronze events to silver layer.
    - Apply data quality rules
    - Standardize field formats
    - Parse JSON payloads
    """
    payload_schema = "page STRING, amount DOUBLE, item STRING"
    
    return (
        dlt.read_stream("bronze_raw_events")
        # Standardize text fields
        .withColumn("id", F.trim(F.col("id")))
        .withColumn("event_type", F.lower(F.trim(F.col("event_type"))))
        .withColumn("source_system", F.upper(F.coalesce(F.col("source_system"), F.lit("UNKNOWN"))))
        # Parse JSON payload
        .withColumn("payload_parsed", F.from_json(F.col("payload"), payload_schema))
        .withColumn("page", F.col("payload_parsed.page"))
        .withColumn("amount", F.col("payload_parsed.amount"))
        .withColumn("item", F.col("payload_parsed.item"))
        # Add metadata
        .withColumn("_silver_processed_at", F.current_timestamp())
        # Select final columns
        .select(
            "id",
            "event_type",
            "event_timestamp",
            "source_system",
            "page",
            "amount",
            "item",
            "_ingestion_timestamp",
            "_silver_processed_at"
        )
    )


@dlt.table(
    name="silver_events_deduplicated",
    comment="Deduplicated silver events - one record per ID",
    table_properties={
        "quality": "silver"
    }
)
def silver_events_deduplicated():
    """
    Deduplicated view of silver events.
    Keeps the most recent record per ID.
    """
    from pyspark.sql.window import Window
    
    window_spec = Window.partitionBy("id").orderBy(F.col("event_timestamp").desc())
    
    return (
        dlt.read("silver_events")
        .withColumn("_row_num", F.row_number().over(window_spec))
        .filter(F.col("_row_num") == 1)
        .drop("_row_num")
    )


# =============================================================================
# Data Quality Metrics
# =============================================================================

@dlt.table(
    name="silver_dq_metrics",
    comment="Data quality metrics for silver layer"
)
def silver_dq_metrics():
    """
    Track data quality metrics over time.
    """
    return (
        dlt.read("silver_events")
        .withColumn("event_date", F.to_date("event_timestamp"))
        .groupBy("event_date")
        .agg(
            F.count("*").alias("total_records"),
            F.sum(F.when(F.col("amount").isNull(), 1).otherwise(0)).alias("null_amounts"),
            F.countDistinct("id").alias("unique_ids"),
            F.countDistinct("event_type").alias("unique_event_types")
        )
        .withColumn("_metrics_timestamp", F.current_timestamp())
    )
