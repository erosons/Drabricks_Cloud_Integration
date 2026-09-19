from pyspark import pipelines as dp
from pyspark.sql.functions import col

# Handles scenario were multiple sources are feeding into a single table
dp.create_streaming_table(
    name="shippers",
    table_properties={
        "pipelines.owner": "pipelines",
        "quality": "bronze",
        "delta.autoOptimize.autoCompact": "true",
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.enableDeletionVectors": "true"
        }
    )

#feed 1 in customer_region1
@dp.append_flow(target = "shippers")
def shipper_1():
  return (
    spark.readStream.table("mysandbox.dl_northwind.shippers")
  )

#feed 2 in customer_region2
@dp.append_flow(target = "shippers")
def shipper_2():
  return (
    spark.readStream.table("mysandbox.dl_northwind.shippers2")
  )
