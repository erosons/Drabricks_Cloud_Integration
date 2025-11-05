from pyspark import pipelines as dp
from pyspark.sql import functions as F
from importlib.resources import files, as_file
from Utilities.yaml_parser import load_yaml
import json
import os

# This is a place holder to perform all the necessary transformation
@dp.view(
    name = "customer_transform_view"
)
def customer_view_transformation():
    df = (spark.readStream.table("customers")
      .withColumn("email", F.lower(F.col("email_address")))
      .withColumn("email", F.regexp_replace(F.col("email_address"), "@gmail.com", "@yahoo.com"))
      .withColumn("last_updated_date", F.current_timestamp())
      )
    return df

dp.create_streaming_table("silver.customer_silver_table")


# This is an upsert operation we will apply SCD Type1
dp.create_auto_cdc_flow(
  target = "silver.customer_silver_table",
  source = "customer_transform_view",
  keys = ["id"],
  sequence_by = F.col("id"), # usually by time timestamp
  stored_as_scd_type = "1",
  apply_as_deletes = None, # Scenarios where we want to delete the data based on deleetion from source
  except_column_list = None,
  track_history_except_column_list = None
)