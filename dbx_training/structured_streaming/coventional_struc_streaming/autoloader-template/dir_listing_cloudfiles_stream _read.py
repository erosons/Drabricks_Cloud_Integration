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

# Scenario where the pre-schema exists, schema is pre-read and fed into the readStream
# this could be reading from a schema registry
schema =spark.read \
.json('s3://acm-test-bucket/AutoLoader/schema_location/') \
.schema


# reading files from path
## When the schema is inferred , it is all inferred as string and loaded to specified location as specified on line 4
streamdf = spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format','json') \
                .option("path",'s3://acm-test-bucket/sanbox2/') \
                .option("maxFilesPerTrigger", 1) \
                .load()

streamdf = spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format','json') \
                .schema(schema) \
                .option("path",'s3://acm-test-bucket/sanbox2/') \
                .option("maxFilesPerTrigger", 1) \
                .load()

#transformation layer
streamdf =streamdf \
         .withColumn('created_year',year('created_at')) \
         .withColumn('created_month',month('created_at'))\
         .withColumn('created_dayofmonth',date_format('created_at','dd'))


# ###########################################    
# writing files to path object storage
# ###########################################   
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
#  Loading incremental Files
###########################

# All the process as above remain the same
"""
NOTE: There might be scenario we might run in schema merge issues with incremental loader , simple add merge Schema
"""
    
streamdf. \
    writeStream. \
     partitionBy('created_year', 'created_month','created_dayofmonth')\
    .format('delta') \
    .option("checkpointLocation", "s3://extertables-loc/cloudfiles/checkpoint") \
    .option("path", "s3://extertables-loc/cloudfiles/stream") \
    .option('mergeSchema','true') \
    .trigger(once=True) \
    .start()

# #########################
#  DLT with Expectation
###########################

json_path =''

# Ingestion later -Bronze layer
@dlt.create_table(
)
def clickstream_table():
  return (spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format','json') \
                .schema(schema) \
                .option("path",'s3://acm-test-bucket/sanbox2/') \
                .option("maxFilesPerTrigger", 1) \
                .load()
  )

#Clean and prepare data -Silver layer
@dlt.table('clickstream_table')
@dlt.expect("valid_timestamp", 'current_timestamp < now()')
@dlt.expect_or_fail('valid_timestamp', 'timestamp < now()')
def clickstream_table_with_expectations():
  return (
    dlt.read('clickstream_table')
    .withColumn('current_timestamp', current_timestamp())
    .withColumnRenamed ('timestamp', 'current_timestamp')
    .select('current_timestamp', 'current_timestamp')
  )

  # Data Product- Gold layer
@dlt.table(
    comment=' This is the gold layer of the clickstream data'
    )
def clickstream_table_gold():
    return (
       dlt.read('clickstream_table_with_expectations')
      .filter('current_timestamp < now()')
      .select('current_timestamp')
      .limit(100)
    )