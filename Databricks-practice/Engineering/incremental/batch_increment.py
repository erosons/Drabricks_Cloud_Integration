# Databricks notebook source
from databricks.connect import DatabricksSession
import dlt
from utils.file_managment import *
import os
from dataclasses import dataclass
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




@dataclass
class IncrementalLoader:
    """Class for keeping track of an item in inventory."""

    def incremental_load(
        self,
        source_file_format: FileFormat = None,
        table_name: str = None,
        schema_name: str = None,
        catalog_name: str = None,
        files_source_path: str = None
    ):
        """Method to perform incremental load into Delta table.
        automat tuned file size:https://learn.microsoft.com/en-us/azure/databricks/delta/tune-file-size
        source_file_format: FileFormat
            The format of the source files (e.g., 'csv', 'json', 'parquet').
        table_name: str
            The name of the target Delta table.
        schema_name: str
            The schema name where the target table resides.
        catalog_name: str
            The catalog name where the target table resides.
        files_source_path: str
            The path to the source files to be loaded.

        returns: None

        """

        if not spark._jsparkSession.catalog().tableExists(f""" {catalog_name}.{schema_name}.{table_name} """):
            if table_name and schema_name and catalog_name:
                spark.sql(
                    """
                    CREATE TABLE IF NOT EXISTS {catalog_name}.{schema_name}.{table_name}

                    COPY INTO {catalog_name}.{schema_name}.{table_name}
                    FROM '{files_source_path}'
                    FILEFORMAT = '{source_file_format}'
                    FORMAT_OPTIONS ('header' = 'true')
                    COPY_OPTIONS ('mergeSchema' = 'true')
                    """
                )
            raise ValueError("tables definition not provide.")

        else:
            spark.sql(
                f"""
                    COPY INTO {catalog_name}.{schema_name}.{table_name}
                    FROM '{files_source_path}'
                    FILEFORMAT = '{source_file_format}'
                    FORMAT_OPTIONS ('header' = 'true')
                    COPY_OPTIONS ('mergeSchema' = 'true')
                    """
            )
            print("Table exists. Proceeding with incremental load...")
            # Add your incremental load logic here