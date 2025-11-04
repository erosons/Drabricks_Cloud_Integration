# Databricks notebook source
# MAGIC %md
# MAGIC ###  For streaming sources 
# MAGIC <p>Files,tables,Streamimg tables,messages CDF</p>
# MAGIC - Streaming  -> Siver layer(Append flow ) -> Gold layer (Sink can only talk onr more append Flow) <br>
# MAGIC - Streaming  -> Siver layer(Auto CDC for Type 1or 2 ) -> Gold layer (Streaming table(Apendflow or AutoCDC))
# MAGIC <br>
# MAGIC
# MAGIC ### Batch Sources
# MAGIC - Streaming  -> Siver layer(MV Flow) -> Gold layer (material Taget)

# COMMAND ----------

import sys

sys.path.append('/Workspace/Users/Drabricks_Cloud_Integration/Databricks-practice/Engineering/incremental/utils')

# COMMAND ----------

from databricks.connect import DatabricksSession
from pyspark import pipelines as dp
from datetime import datetime
import os
from dataclasses import dataclass
from utils.file_managment import *
from pyspark.sql.functions import (
    col,
    input_file_name,
    lit,
    current_timestamp,
    struct,
    sum,
    count
)
from pyspark.sql.types import StructType, StructField, StringType, TimestampType
from typing import Optional

files_source_path ='abfss://samson-databricks-container-8@samstorage8.dfs.core.windows.net/raw'

# CLUSTER_ID: str = os.getenv('DBX_CLUSTER_ID')

# spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
# spark.sql("""SET spark.sql.files.maxRecordsPerFile = 1000000;""")



@dp.table(
    name="bronze_incremental_table",
    comment="Incrementally loaded table using DLT",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true",
        'delta.enableDeletionVectors' : 'true'
    }
)
def load_incremental_data():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.useNotifications", "true") 
        .options("cloudFiles.useManagedFileEvents", True)
        .option("header", "true")
        .option("cloudFiles.schemaEvolutionMode","addNewColumns")   # evolve schema
        .option("rescuedDataColumn","_rescue")                      # keep bad columns
        .load(files_source_path) 
        .withColumn(
                    "metadata",
                    struct(
                         col("_metadata.file_name").alias(metadataColumns.SOURCE_FILE.value),
                        current_timestamp().alias(metadataColumns.CREATED_DATE.value),
                        lit("source_system").alias(StorageType.ADLS.value)
                    )
                )
        )

# @AUTOCDC wit Fivetran or lakeflow connector with SCD2
# dlt.create_streaming_table(name="silver_cdc", table_properties={"quality":"silver"})

# from pyspark.sql.functions import col, expr
# dlt.apply_changes(
#     target                 = "silver_cdc",
#     source                 = "bronze_events",   # your CDC bronze
#     keys                   = ["id"],
#     sequence_by            = col("_commit_ts"), # or your ordering column
#     apply_as_deletes       = expr("op = 'DELETE'"),
#     except_column_list     = ["op", "_commit_ts", "_valid_from", "_valid_to"],
#     track_history_columns  = ["_commit_ts"]
# )


# COMMAND ----------

def parse(df):
    return (
        df
        .withColumn("processed_timestamp", current_timestamp())
        .withColumn("source_system", lit(StorageType.ADLS.value))
        .withColumn("Profit", col("Profit").cast("float"))
        .withColumn("Sales", col("Sales").cast("float"))
        .withColumn("Quantity", col("Quantity").cast("int"))
    )

@dp.table(
    name="silver_incremental_table",
    comment="Incrementally loaded table using DLT",
    table_properties={
        "quality": "silver",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true",
        'delta.enableDeletionVectors' : 'true'
    }
)
def silver_load_incremental_data():
    df = (
        spark.readStream.table("bronze_incremental_table")
        .transform(parse)
        .withColumn(str(metadataColumns.PROCESSING_TIMESTAMP.value), current_timestamp())
    )
    return df

# COMMAND ----------

from pyspark.sql.functions import date_trunc
from pyspark import pipelines as dp

#https://www.databricks.com/blog/optimizing-materialized-views-recomputes
#https://www.databricks.com/blog/introducing-materialized-views-and-streaming-tables-databricks-sql
#Enzyme Compute Engine
# Limitation : https://docs.databricks.com/aws/en/ldp/dbsql/materialized

@dp.materialized_view(
    #   name="<name>",
    #   comment="<comment>",
    #   spark_conf={"<key>" : "<value>", "<key>" : "<value>"},
    #   table_properties={"<key>" : "<value>", "<key>" : "<value>"},
    #   path="<storage-location-path>",
    #   partition_cols=["<partition-column>", "<partition-column>"],
    #   cluster_by_auto = True,
    #   cluster_by = ["<clustering-column>", "<clustering-column>"],
    #   schema="schema-definition",
    #   row_filter = "row-filter-clause",
    name="gold_sales",
    table_properties={"quality":"gold",
                      'delta.enableRowTracking' : 'true',
                      'delta.enableDeletionVectors' : 'true'}
)
def gold_sales():
    s = spark.read.table("silver_incremental_table")
    return (
        s.groupBy(
            col("CustomerID"),
            date_trunc('day',col("OrderDate")).alias("event_day")
        )
        .agg(
            sum("Sales").alias("total_amount"),
            count("*").alias("txn_cnt")
        )
    )

