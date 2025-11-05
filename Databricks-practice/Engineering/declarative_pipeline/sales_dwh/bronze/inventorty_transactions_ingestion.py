from pyspark import pipelines as dp
from pyspark.sql import functions as F  


# Please edit the sample below

@dp.table(
    name="inventory_transactions",
    comment="Streaming table",
    table_properties={
        "quality": "bronze",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.enableDeletionVectors": "true"
    }
)
def inventory_transactions():
    raw = (
        spark.readStream.table("mysandbox.dl_northwind.inventory_transactions")
        .withColumn(
                    "metadata",
                    F.struct(
                        F.col("_metadata.file_name").alias("data_source"),
                        F.col("_metadata.file_modification_time").alias("file_created_time"),
                        F.lit("source_system").alias("mysandbox.dl_northwind.inventory_transactions")
                    )
        )
    )
    return raw