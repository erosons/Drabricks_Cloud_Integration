from pyspark import pipelines as dp
from pyspark.sql import functions as F


dp.create_streaming_table("silver.order_details_silver")


# This is an upsert operation we will apply SCD Type1
dp.create_auto_cdc_flow(
  target = "silver.order_details_silver",
  source = "order_details",
  keys = ["id"],
  sequence_by = F.col("id"), # usually by time timestamp
  stored_as_scd_type = "1",
  apply_as_deletes = None, # Scenarios where we want to delete the data based on deleetion from source
  except_column_list = None,
  track_history_except_column_list = None
)