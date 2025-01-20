from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession, Row
from spark_readstream import socket_streamimng
import os
import json

WORKSPACE_URL: str = os.getenv("databricks_workspaceURL")
print(WORKSPACE_URL)
CLUSTER_ID: str = os.getenv("clusterID")
_token = os.getenv("PAT")

# 4 Types of Trigger in a structured Streaming
"""
unspecified(default), After it processes a batch it will not sleep instead will stat process another batch
continous :Can process records in milliseconds that would otherwise take seconds in micro batch
microbatch/At regular frequency : processTime =1 which is the time it will ask for another checkpoint
Once -trigger(once=triue)

"""

# Option 1:Working or parameters are fulled from the dbconfig #
spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()

streamDF = socket_streamimng()

def write_stream_to_console():
    
    # Note is not trigger is not specified the stream will read a microbatch and start the next microbatch
    streamDF.writeStream \
    .outputMode("append") \
    .format("console") \
    .trigger(processingTime="5 seconds") \
    .start()

def write_stream_to_file():
    #checkpointLocation: 
    streamDF.writeStream \
    .format("csv") \
    .option("checkpointLocation", "s3://extertables-loc/project1/checkpoint") \
    .option("path", "s3://extertables-loc/project1/stream") \
    .trigger(processingTime="10 seconds") \
    .start()
if __name__ == "__main__":
   write_stream_to_file()