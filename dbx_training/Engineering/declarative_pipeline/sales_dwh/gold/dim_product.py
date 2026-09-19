from pyspark import pipelines as dp
from pyspark.sql import functions as F
# from importlib.resources import files, as_file
# from Utilities.yaml_parser import load_yaml
# import json
# import os

dp.create_streaming_table("gold.dim_products")


# This is an upsert operation we will apply SCD Type2
dp.create_auto_cdc_flow(
  target = "gold.dim_products",
  source = "product_transform_view", # will continually return new data from this view
  keys = ["id"],
  sequence_by = F.col("last_updated_date"), # usually by time timestamp
  stored_as_scd_type = "2",
  apply_as_deletes = None, # Scenarios where we want to delete the data based on deleetion from source
  except_column_list = None,
  track_history_except_column_list = None
)