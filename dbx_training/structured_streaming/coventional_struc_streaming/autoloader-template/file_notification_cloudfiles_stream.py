"""
Setup Events notification on s3 properties
- delete events 
- Create events (put ,post,copy,multiparts)
- updates propers of s3

WHen an events happen on s3 and notification will be sent by SNS 

Simple Architecture Overview

s3(A2A/A2P) events notification is publish to AWS SNS  ==> SNS Topic( decouple publisher from subcribers) =>[AWS lambda, AWS SQS, http(s) endpoint etc]'

The cloudfiles notification checks the SQ for new files and process instead of listding thorugh  huge files. , 
"""


from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession, Row
from pyspark.sql.functions import to_date,month,year,date_format
import os
import json

WORKSPACE_URL: str = os.getenv("databricks_workspaceURL")
print(WORKSPACE_URL)
CLUSTER_ID: str = os.getenv("clusterID")
_token = os.getenv("PAT")

# Option 1:Working or parameters are filled from the dbconfig #
spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()

# reading files from path
## When the No schema registery exists, it is all inferred as string and loaded to specified location as specified on line 4
streamdf = spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format','json') \
                .option('cloudFiles.useNotifications','true') \
                .option("path",'s3://acm-test-bucket/sanbox2/') \
                .option("checkpointLocation", "s3://extertables-loc/cloudfiles/checkpoint") \
                .option('cloudFiles.region', 'us-east-1SS') \
                .option("maxFilesPerTrigger", 1) \
                .load()

# Scenario where the pre-schema exists, schema is pre-read and fed into the readStream
# this could be reading from a schema registry
schema =spark.read \
.json('s3://acm-test-bucket/AutoLoader/schema_location/') \
.schema

streamdf = spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format','json') \
                .option('cloudFiles.useNotifications','true') \
                .schema(schema) \
                .option("path",'s3://acm-test-bucket/sanbox2/') \
                .option('cloudFiles.region', 'us-east-1') \
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
    .option("checkpointLocation", "s3://extertables-loc/cloudfiles/checkpoint") \
    .option("path", "s3://extertables-loc/cloudfiles/stream") \
    .trigger(once=True) \
    .start()

#Reading the delta Files
df = spark.read \
    .format("delta") \
    .load("s3://extertables-loc/cloudfiles/stream")
display(df)


# #########################
# Loading incremental Files
###########################

# All the process as above remain the same
"""
NOTE: There might be scenario we might run in schema merge issues with incremental loader , simple add merge Schema
"""
    
streamdf = spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format','json') \
                .option('cloudFiles.useNotification','true') \
                .schema(schema) \
                .option("path",'s3://acm-test-bucket/sanbox2/') \
                .option('cloudFiles.region', 'us-east-2') \
                .option("maxFilesPerTrigger", 1) \
                .load()

# transformation layer
streamdf =streamdf \
         .withColumn('created_year',year('created_at')) \
         .withColumn('created_month',month('created_at'))\
         .withColumn('created_dayofmonth',date_format('created_at','dd'))
    
# writing files to path object storage
streamdf. \
    writeStream. \
     partitionBy('created_year', 'created_month','created_dayofmonth')\
    .format('delta') \
    .option("checkpointLocation", "s3://extertables-loc/cloudfiles/checkpoint") \
    .option("path", "s3://extertables-loc/cloudfiles/stream") \
    .trigger(once=True) \
    .start()

#Reading the delta Files
df = spark.read \
    .format("delta") \
    .load("s3://extertables-loc/cloudfiles/stream")
display(df)

