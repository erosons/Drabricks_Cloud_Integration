from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import year,month,date_format
from spark_readstream import socket_streamimng
import os
import json

WORKSPACE_URL: str = os.getenv("databricks_workspaceURL")
print(WORKSPACE_URL)
CLUSTER_ID: str = os.getenv("clusterID")
_token = os.getenv("PAT")



# Option 1:Working or parameters are fulled from the dbconfig #
spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()


def file_consume(spark,format):
    """
    File Systems: In many cases, files written in directories are monitored by Spark structured
    streaming for new data. This is common with file systems that are HDFS-compatible or cloud storage like S3

    NOTE: option("checkpointLocation", "s3://extertables-loc/project1/checkpoint"): Sets the location where checkpoints
    spark.conf.set('spark.sql.streaming.schemaInference','true') do not use in production define the schema
    are stored. Checkpoints store the current state of your streaming job and are crucial for fault tolerance. If the
    streaming job fails, it can be restarted from the last checkpoint to ensure data integrity. This location is an S3 bucket path.
    """
    # reading files from path
    streamdf = spark.readStream \
                .format(format) \
                .option("path", "/path/to/directory") \
                .option("maxFilesPerTrigger", 1) \
                .load()
    
    #transformation layer
    streamdf =streamdf \
         .withColumn('created_year',year('created_at')) \
         .withColumn('created_month',month('created_at'))\
         .withColumn('created_dayofmonth',date_format('created_at','dd'))
    
    # writing files to path object storage
    streamdf. \
    writeStream. \
     partitionBy('created_year', 'created_month','created_dayofmonth')\
    .format('delta') \
    .option("checkpointLocation", "s3://extertables-loc/project1/checkpoint") \
    .option("path", "s3://extertables-loc/project1/stream") \
    .trigger(once=True) \
    .start()


    # Downstream transactions
    # Executing read 
df = spark.read \
    .format("delta") \
    .load("s3://extertables-loc/project1/ghactivity")
display(df)





# DOWN STREAM OPERATION LIKE CREATING TABLE

spark.sql(f"DROP TABLE IF EXISTS projecta.sales.delta2")
df = spark.sql(f"CREATE TABLE IF NOT EXISTS projecta.sales.delta2 USING DELTA LOCATION 's3://extertables-loc/project1/ghactivity'")
df.show()

## Written in spark sql and Dataframe API
dfs.filter("type ='CreateEvent' AND payload.ref_type='repository'").count()
display(spark.sql("SELECT count(*) from demo where type='CreateEvent' AND payload.ref_type='repository'"))

from pyspark.sql.functions import to_date
display(dfs.groupBy(to_date('created_at')).count())
display(spark.sql("SELECT count(*) from demo group by cast(created_at as date)"))