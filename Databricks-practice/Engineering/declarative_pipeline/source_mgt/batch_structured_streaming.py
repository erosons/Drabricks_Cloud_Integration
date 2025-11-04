# For streaming sources
# Files,tables,Streamimg tables,messages CDF

# - Streaming -> Siver layer(Append flow ) -> Gold layer (Sink can only talk one more append Flow)
# - Streaming -> Siver layer(Auto CDC for Type 1or 2 ) -> Gold layer (Streaming table(Apendflow or AutoCDC))
# Batch Sources
# Streaming -> Siver layer(MV Flow) -> Gold layer (material_view Taget)

from pyspark import pipelines as dp        # keep your dp alias
from pyspark.sql import functions as F
from pyspark.sql import Window
from Utilities.file_parser import (
    Transformer
)

# --------- CONFIG ----------
files_source_path = "abfss://samson-databricks-container-8@samstorage8.dfs.core.windows.net/staging_zone"


# If you use these enums in your codebase, keep them; otherwise replace with strings.
# from your_module import metadataColumns, StorageType

# --------- BRONZE (streaming) ----------
@dp.table(
    name="bronze_incremental_table",
    comment="Incrementally loaded bronze table using Auto Loader with window-based de-dup",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.enableDeletionVectors": "true"
    }
)
def bronze_incremental_table():
    raw =(
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("header", "true")
        # Use managed events only if you’ve fixed RBAC; else comment this out:
        .option("cloudFiles.useManagedFileEvents", "true")
        .option("cloudFiles.schemaEvolutionMode", "addNewColumns")
        .option("rescuedDataColumn", "_rescue")
        .load(files_source_path)
        .withColumn(
            "metadata",
            F.struct(
                 F.col("_metadata.file_name").alias("data_source"),
                 F.col("_metadata.file_modification_time").alias("file_created_time"),
                F.lit("source_system").alias("ADLS")
            )
        )
    )
    return raw


# --------- SILVER (streaming from bronze) ----------
@dp.table(
    name="silver_incremental_table",
    comment="Typed, cleaned streaming table from bronze",
    table_properties={
        "quality": "silver",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.enableDeletionVectors": "true",
        "delta.enableRowTracking": "true",
        "delta.enableChangeDataFeed" : "true"
    }
)
def silver_incremental_table():
    return (
        spark.readStream.table("bronze_incremental_table")
        .transform(Transformer.parse)
        .withColumn("processing_timestamp", F.current_timestamp())
    )
        # Example window: deduplicate by CustomerID, OrderDate, keeping earliest by OrderDate


#https://www.databricks.com/blog/optimizing-materialized-views-recomputes
#https://www.databricks.com/blog/introducing-materialized-views-and-streaming-tables-databricks-sql
#Enzyme Compute Engine
# Limitation : https://docs.databricks.com/aws/en/ldp/dbsql/materialized
# --------- GOLD (aggregated) ----------
# If your environment supports dp.materialized_view; if not, change to @dp.table

@dp.materialized_view(
    name="gold_sales",
    table_properties={
        "quality": "gold"
    }
)
def gold_sales():
        # SELECT
        #     timestamp,
        #     message
        # FROM event_log(TABLE(main.default.gold_sales))
        # WHERE event_type = 'planning_information'
        # ORDER BY timestamp DESC; -> use the query above to check if there was an incremental load or full refresh
    s = spark.read.table("silver_incremental_table")
    return (
        s.groupBy(
            F.col("CustomerID"),
            F.date_trunc("day", F.col("OrderDate")).alias("event_day")
        )
        .agg(
            F.sum("Sales").alias("total_amount"),
            F.count(F.lit(1)).alias("txn_cnt")
        )
    )
