# Databricks notebook source
from databricks.connect import DatabricksSession
import dlt
from datetime import datetime
import os
from dataclasses import dataclass
from utils.file_managment import *
from pyspark.sql import (
    col,
    input_file_name,
    lit,current_timestamp
    )
from pyspark.types import StructType
from typing import Optional


CLUSTER_ID: str = os.getenv('DBX_CLUSTER_ID')

spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
spark.sql("""SET spark.sql.files.maxRecordsPerFile = 1000000;""")



@dlt.table(
    name="bronze_incremental_table",
    comment="Incrementally loaded table using DLT",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true"
    }
)
def load_incremental_data():
    return (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "csv")
        .option("cloudFiles.useNotifications", "true") 
        .option("header", "true")
        .load("{files_source_path}') ")
        .withColumn("metadata",
                StructType(
                        input_file_name().alias(metadataColumns.SOURCE_FILE.value),
                        current_timestamp().alias(metadataColumns.CREATED_DATE.value),
                        lit("source_system").alias(StorageType.ADLS.value))
    )
    )

# COMMAND ----------

@dlt.table(
    name="silver_incremental_table",
    comment="Incrementally loaded table using DLT",
    table_properties={
        "quality": "silver",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true"
    }
)
def silver_load_incremental_data():
    time_tracker = ProcesTime()
    time_tracker.start_time
    
    df = spark.read. format("{self.destination_format}") \
        .table("bronze_incremental_table") \
        .withColumn("processed_timestamp", col("current_timestamp()")) \
        .withColumn("source_system", col("'ADLS'")) \
        .withColumn("Profit",col("Profit").cast("float")) \
        .withColumn("Sales",col("Sales").cast("float")) \
        .withColumn("Quantity",col("Quantity").cast("int")) \
        .withColumn("metadata",
                StructType(
                    current_timestamp().alias(metadataColumns.CREATED_DATE),
                )
        )
    time_tracker.end_time = datetime.now()

    return df.withColumns(time_tracker.duration_in_seconds().alias(metadataColumns.PROCESSING_TIMESTAMP))

# COMMAND ----------
