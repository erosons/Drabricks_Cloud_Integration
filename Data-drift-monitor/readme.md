Step1 : OPTIMIZE db.raw_events ZORDER BY (timestamp);

Step2:
from pyspark.sql.functions import col, date_trunc, count, min, max, isnan

# Load source table
df = spark.read.table("db.raw_events")

# Extract day from timestamp
df_daily = df.withColumn("event_day", date_trunc("DAY", col("timestamp")))

# Aggregate daily metrics
metrics_df = df_daily.groupBy("event_day").agg(
    count("*").alias("row_count"),
    count(col("timestamp")).alias("non_null_count"),
    min("timestamp").alias("min_ts"),
    max("timestamp").alias("max_ts")
)

# Save metrics to drift table
metrics_df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable("db.drift_metrics")

Step3: OPTIMIZE db.drift_metrics ZORDER BY (event_day);

Step4: Visualize in Databricks SQL Dashboard
SELECT 
  event_day, 
  row_count, 
  non_null_count, 
  min_ts, 
  max_ts 
FROM db.drift_metrics 
ORDER BY event_day

#### Chart 
Line chart of row_count over time (drift in volume)

Bar chart comparing non_null_count vs row_count

Heatmap if hourly breakdown is added

Step6:

Calculate % change in row count:

SELECT 
  event_day,
  row_count,
  lag(row_count) OVER (ORDER BY event_day) AS previous,
  (row_count - lag(row_count) OVER (ORDER BY event_day)) / lag(row_count) OVER (ORDER BY event_day) * 100 AS percent_change
FROM db.drift_metrics


step7:
Set up alerts in Databricks SQL if row_count drops suddenly or nulls increase

