%python
import dlt
from pyspark.sql.functions import *

# Define the path to your ADLS container and the folder
external_location ='abfss://westuccontainer2@databrickwest001.dfs.core.windows.net/IngestionData/streamloc'
cloudFilesFormat = "csv"

@dlt.table(
    comment="Raw data ingestion from test_catalog.saleslt.customer",
    table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true",
        'delta.deletedFileretentionDuration' : "30 days"
    }
)
def customer_bronze():
    stream_df = spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format', cloudFilesFormat) \
                .option("cloudFiles.useIncrementalListing", "true") \
                .option("cloudFiles.inferColumnTypes", "true") \
                .option("maxFilesPerTrigger", 1) \
                .load(external_location)
    return (
        stream_df.withColumn("file_name", col("_metadata.file_path"))
                 .withColumn("updated", current_timestamp())
    )