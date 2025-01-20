from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession, Row
import os
import json

WORKSPACE_URL: str = os.getenv("databricks_workspaceURL")
print(WORKSPACE_URL)
CLUSTER_ID: str = os.getenv("clusterID")
_token = os.getenv("PAT")

"""
Spark Stream exposes direct API : json,csv,parquet,orc
    spark.readStream.json(filepath)
    spark.readStream.parquet(filepath)
    spark.readStream.csv(filepath)
Use can Format
    spark.readStream.format('csv').load()

NOTE : When reading json format, you have to define the schema
spark.conf.set('spark.sql.streaming.schemaInference','true) -> can be used for development purposely for PROD defines schema
"""

# Option 1:Working or parameters are fulled from the dbconfig #
spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()

def socket_streamimng():
    """
    description:
    show() will throw exception with read stream dataframe instead writeStream.start() should be used 
    Validating streamDf.isStreaming -> Boolaean
    Schema check  streamDF.printSchema()
    """
    streamDF = spark.readStream \
            .format("socket") \
            .option("host" ,"localhost") \
            .option("port", 9090) \
            .load()
    return streamDF


def kaka_consume(spark):
    """
    To read from a Kafka source in Spark Structured Streaming, you would configure it as follows:
    """
    streamDF = spark.readStream \
            .format("kafka") \
            .option("kafka.bootstrap.servers", "host1:port1,host2:port2") \
            .option("subscribe", "topic-name") \
            .load()
    return streamDF


def kinesis_consume(spark):
    """
    Amazon Kinesis: Kinesis is often used in AWS environments for real-time data streaming.
    It can collect, process, and analyze streaming data similar to Kafka.
    """
    streamDF = spark.readStream \
                .format("kinesis") \
                .option("streamName", "your-stream-name") \
                .option("endpointUrl", "https://kinesis.region.amazonaws.com") \
                .option("region", "region-name") \
                .option("initialPosition", "latest") \
                .load()
    return streamDF

def file_consume(spark,format):
    """
    File Systems: In many cases, files written in directories are monitored by Spark structured
    streaming for new data. This is common with file systems that are HDFS-compatible or cloud storage like S3
    """
    streamDF = spark.readStream \
                .format(format) \
                .option("path", "/path/to/directory") \
                .option("maxFilesPerTrigger", 1) \
                .load()
    return streamDF


if __name__ == "__main__":
     socket_streamimng()