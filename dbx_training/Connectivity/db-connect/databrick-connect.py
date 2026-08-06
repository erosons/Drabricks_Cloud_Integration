# Set the Spark Connect connection string in DatabricksSession.builder.remote. 
# comes with pysaprk.sql
from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession
import os

WORKSPACE_URL:str = os.getenv('databricks_workspaceURL')
print(WORKSPACE_URL)
CLUSTER_ID:str = os.getenv('clusterID')
_token = os.getenv('PAT')

# Option 1:Working or parameters are fulled from the dbconfig #
spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
df = spark.read.table("samples.nyctaxi.trips")
df.show(5)


# Option 3:Working Using a simple conn_string
spark = DatabricksSession.builder.remote(
    host= WORKSPACE_URL,
    token = _token,
    cluster_id=CLUSTER_ID
    ).getOrCreate()


df = spark.read.table("samples.nyctaxi.trips")
df.show(5)

# # Option 2 Using a simple conn_string: revisit not working
# conn = f"sc://{WORKSPACE_URL}/;token={_token};x-databricks-cluster-id={CLUSTER_ID}" # noqa: E501

# spark = DatabricksSession.builder.remote(conn).getOrCreate()
# df = spark.read.table("samples.nyctaxi.trips")
# df.show(5)
