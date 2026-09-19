# Databricks notebook source
# MAGIC %md
# MAGIC # Gold Layer - Business Aggregations
# MAGIC 
# MAGIC This notebook creates business-ready aggregated views and summary tables.
# MAGIC 
# MAGIC **Layer:** Gold (Business)  
# MAGIC **Pattern:** Overwrite or Merge aggregations  
# MAGIC **Data Quality:** Business rules applied, ready for consumption

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
from datetime import datetime, timedelta

spark.sql(f"USE CATALOG {catalog}")
spark.sql(f"USE SCHEMA {schema}")

processing_timestamp = datetime.now()
print(f"Processing Timestamp: {processing_timestamp}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Read Silver Data

# COMMAND ----------

silver_table = "silver_events"
silver_df = spark.table(silver_table)

print(f"Silver records available: {silver_df.count()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold Table 1: Daily Event Summary

# COMMAND ----------

daily_summary_df = silver_df \
    .withColumn("event_date", F.to_date("event_timestamp")) \
    .groupBy("event_date", "event_type", "source_system") \
    .agg(
        F.count("*").alias("event_count"),
        F.countDistinct("id").alias("unique_events"),
        F.sum("amount").alias("total_amount"),
        F.avg("amount").alias("avg_amount"),
        F.min("event_timestamp").alias("first_event"),
        F.max("event_timestamp").alias("last_event")
    ) \
    .withColumn("_gold_processed_at", F.lit(processing_timestamp))

display(daily_summary_df)

# COMMAND ----------

# Write daily summary
gold_daily_table = "gold_daily_event_summary"

daily_summary_df.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(gold_daily_table)

print(f"Written to: {catalog}.{schema}.{gold_daily_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold Table 2: Event Type Metrics

# COMMAND ----------

event_metrics_df = silver_df \
    .groupBy("event_type") \
    .agg(
        F.count("*").alias("total_events"),
        F.countDistinct("id").alias("unique_events"),
        F.countDistinct("source_system").alias("source_count"),
        F.sum("amount").alias("total_revenue"),
        F.avg("amount").alias("avg_revenue"),
        F.min("event_timestamp").alias("first_seen"),
        F.max("event_timestamp").alias("last_seen")
    ) \
    .withColumn("_gold_processed_at", F.lit(processing_timestamp))

display(event_metrics_df)

# COMMAND ----------

# Write event metrics
gold_metrics_table = "gold_event_type_metrics"

event_metrics_df.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(gold_metrics_table)

print(f"Written to: {catalog}.{schema}.{gold_metrics_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Gold Table 3: Rolling Window Metrics (7-Day)

# COMMAND ----------

# Calculate 7-day rolling metrics
window_7d = Window \
    .partitionBy("event_type") \
    .orderBy("event_date") \
    .rowsBetween(-6, 0)

rolling_metrics_df = silver_df \
    .withColumn("event_date", F.to_date("event_timestamp")) \
    .groupBy("event_date", "event_type") \
    .agg(
        F.count("*").alias("daily_count"),
        F.sum("amount").alias("daily_amount")
    ) \
    .withColumn("rolling_7d_count", F.sum("daily_count").over(window_7d)) \
    .withColumn("rolling_7d_amount", F.sum("daily_amount").over(window_7d)) \
    .withColumn("rolling_7d_avg", F.avg("daily_count").over(window_7d)) \
    .withColumn("_gold_processed_at", F.lit(processing_timestamp))

display(rolling_metrics_df)

# COMMAND ----------

# Write rolling metrics
gold_rolling_table = "gold_rolling_metrics"

rolling_metrics_df.write \
    .format("delta") \
    .mode("overwrite") \
    .option("overwriteSchema", "true") \
    .saveAsTable(gold_rolling_table)

print(f"Written to: {catalog}.{schema}.{gold_rolling_table}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Create Business Views

# COMMAND ----------

# Create a view for easy consumption by analysts
spark.sql(f"""
    CREATE OR REPLACE VIEW v_executive_dashboard AS
    SELECT 
        event_date,
        SUM(event_count) as total_events,
        SUM(total_amount) as total_revenue,
        COUNT(DISTINCT event_type) as event_types,
        COUNT(DISTINCT source_system) as source_systems
    FROM {gold_daily_table}
    GROUP BY event_date
    ORDER BY event_date DESC
""")

print(f"Created view: {catalog}.{schema}.v_executive_dashboard")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Validation

# COMMAND ----------

# Validate gold tables
tables_to_validate = [gold_daily_table, gold_metrics_table, gold_rolling_table]

validation_results = []
for table in tables_to_validate:
    count = spark.table(table).count()
    validation_results.append({
        "table": table,
        "record_count": count,
        "status": "PASS" if count > 0 else "FAIL"
    })
    print(f"{table}: {count} records")

# Check for any failures
failures = [r for r in validation_results if r["status"] == "FAIL"]
if failures:
    raise Exception(f"Validation failed for tables: {[f['table'] for f in failures]}")

print("\nAll gold tables validated successfully!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Output Metrics

# COMMAND ----------

dbutils.notebook.exit({
    "status": "SUCCESS",
    "tables_created": len(tables_to_validate),
    "validation_results": validation_results,
    "processing_timestamp": str(processing_timestamp)
})
