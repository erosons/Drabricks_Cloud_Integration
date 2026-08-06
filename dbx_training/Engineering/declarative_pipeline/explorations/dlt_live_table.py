

import dlt

@dlt.table(
  name="my_live_table",
  comment="This is a DLT table for batch data processing"
)
def my_batch_table():
    # Read batch data from a Delta Lake
    return spark.read.format("delta").load("/mnt/delta/batch_data")
