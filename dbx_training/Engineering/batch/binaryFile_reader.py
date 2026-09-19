from databricks.connect import DatabricksSession
import os
import json

# If you have a default profile set in your .databrickscfg no additional code
CLUSTER_ID:str = os.getenv('DBX_CLUSTER_ID')

spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()
# Returns Files path and Metadata INFORMATION
df = spark.read.format("binaryFile").load('')

# Register the DataFrame as a temporary view
df.createOrReplaceTempView("json_view")

# Query the temporary view using SQL
result = spark.sql("SELECT * FROM json_view")

# Display the result
print(result)