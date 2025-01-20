# Set the Spark Connect connection string in DatabricksSession.builder.remote.
# comes with pysaprk.sql
from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession
from pyspark.sql.functions import  *
import os


CLUSTER_ID: str = os.getenv("clusterID")


spark = DatabricksSession. \
        builder.\
        clusterId(CLUSTER_ID).\
        getOrCreate()

# for i in dbutils.fs.ls("s3://acm-test-bucket/sandbox/"):
#     print(i.path)
df = spark.read.json(f's3://acm-test-bucket/sandbox/2024-09-30-1.json.gz')
df.printSchema()