from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession,Row
import os
import json

# If you have a default profile set in your .databrickscfg no additional code
# CLUSTER_ID:str = os.getenv('clusterID')
CLUSTER_ID:str = "1028-032656-mbp7bggz"
spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()  #
#spark = DatabricksSession.builder.serverless().getOrCreate()

spark.sql("""SELECT 1""").show()

# external_location:str = spark.sql('describe external location `marketingdata_ingestion`').first()['url'] + '/ingest5'

# def scenario_create_delta_tbl_one():
#     # USE THIS SCENARIO WHEN YOU WANT TO CREATE A DELTA TABLE FROM A SPARK DATAFRAME
#     # FROM PARQUET FILES OR CLEAN DATA
#     df = spark.range(5,11)
#     if spark.catalog.tableExists("unexisting_table")==False:
#         spark.sql(
#         f"""CREATE OR REPLACE TABLE users_pii
#             COMMENT "Contains PII"
#             USING DELTA 
#             LOCATION 's3://extertables-loc/storage -location/'
#             PARTITIONED BY (first_touch_date)
#             AS
#             SELECT *, 
#                 cast(cast(user_first_touch_timestamp/1e6 AS TIMESTAMP) AS DATE) first_touch_date, 
#                 current_timestamp() updated,
#                 input_file_name() source_file
#             FROM parquet."s3://extertables-loc/project1/"
#        """ )
#         spark.sql("COMMENT ON TABLE main.default.users_k IS 'This table contains user data for analysis.'")

#     elif x == True:
#         print("Table already exists")
#         df.write \
#             .format("delta") \
#             .mode('append')\
#             .save(external_location)
                
#     else:
#         df.write \
#             .format("delta") \
#             .option("overwriteSchema", "true") \
#             .option("path", external_location) \
#             .saveAsTable("main.default.users_k")
#         spark.sql("COMMENT ON TABLE main.default.users_k IS 'This table contains user data for analysis.'")

                
