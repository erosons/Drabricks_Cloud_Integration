# Databricks notebook source
# MAGIC %load_ext autoreload
# MAGIC %autoreload 2
# MAGIC # Enables autoreload; learn more at https://docs.databricks.com/en/files/workspace-modules.html#autoreload-for-python-modules
# MAGIC # To disable autoreload; run %autoreload 0

# COMMAND ----------

import sys

import sys

sys.path.append('/Workspace/Users/Drabricks_Cloud_Integration/Databricks-practice/Engineering/utils')

# COMMAND ----------

from databricks.connect import DatabricksSession
from utils.file_managment import *
import os
from dataclasses import dataclass
from pyspark.sql.functions import (
    col,
    input_file_name,
    lit,current_timestamp
    )
from pyspark.sql.types import StructType
from typing import Optional


#CLUSTER_ID: str = os.getenv('DBX_CLUSTER_ID')

# spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
# spark.sql("""SET spark.sql.files.maxRecordsPerFile = 1000000;""")

@dataclass
class BatchLoader:
    """Class for keeping track of an item in inventory."""

    def batch_load(
        self,
        source_file_format:FileFormat = None,
        table_name: str = None,
        schema_name: str = None,
        catalog_name: str = None,
        files_source_path: str = None
    ): 
        """Method to perform batch load into Delta table.
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
        if not spark.catalog.tableExists(f"{catalog_name}.{schema_name}.{table_name}"):
            sql.sql(f"""
                CREATE TABLE IF NOT EXISTS {catalog_name}.{schema_name}.{table_name}
                SELECT * 
                FROM read_files(
                    {files_source_path},
                    format => {source_file_format}
                """
            )


# COMMAND ----------

def main():
    app= BatchLoader()
    app.batch_load(
        source_file_format= FileFormat.CSV.value,
        table_name="bronze",
        schema_name="default",
        catalog_name="main",
        files_source_path='abfss://samson-databricks-container-8@samstorage8.dfs.core.windows.net/raw'
        
    )
if __name__ == "__main__":
    main()

