import dlt
from pyspark.sql.functions import *

@dlt.table(
  name="my_streaming_live_table",
  comment="This is a DLT table for streaming data processing"
)
def my_streaming_table():
    # Ingest streaming data
    return (
        spark.readStream.format("delta")
        .option("maxFilesPerTrigger", 1)  # Optional: Configures micro-batch processing rate
        .load("/mnt/delta/streaming_source")
    )
