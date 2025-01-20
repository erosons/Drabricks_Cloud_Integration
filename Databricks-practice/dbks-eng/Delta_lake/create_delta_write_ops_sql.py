from databricks.connect import DatabricksSession
from pyspark.sql import SparkSession,Row
import os
import json

WORKSPACE_URL:str = os.getenv('databricks_workspaceURL')
print(WORKSPACE_URL)
CLUSTER_ID:str = os.getenv('clusterID')
_token = os.getenv('PAT')

# Option 1:Working or parameters are fulled from the dbconfig #
spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()


def scenario_create_delta_tbl_one():
    # USE THIS SCENARIO WHEN YOU WANT TO CREATE A DELTA TABLE FROM A SPARK DATAFRAME
    # FROM PARQUET FILES OR CLEAN DATA
    df = spark.range(5,11)
    if spark.sql("SHOW TABLES IN main.default LIKE 'users_k'").count() == 0::
        spark.sql(
        f"  CREATE OR REPLACE TABLE users_pii
            COMMENT "Contains PII"
            USING DELTA 
            LOCATION 's3://extertables-loc/storage -location/'
            PARTITIONED BY (first_touch_date)
            AS
            SELECT *, 
                cast(cast(user_first_touch_timestamp/1e6 AS TIMESTAMP) AS DATE) first_touch_date, 
                current_timestamp() updated,
                input_file_name() source_file
            FROM parquet."s3://extertables-loc/project1/"
        )
    else:
        print("Table already exists")
            df.write \
            .format("delta") \
            .mode('append')\
            .save("'s3://extertables-loc/storage -location/'")
            #.save("dbfs:/deltaformat/delta_1")
            df.show()
                
    df.show()


%python
from pyspark.sql.functions import *

external_location = spark.sql('describe external location `marketingdata_ingestion`').first()['url'] + '/ingest5'

def scenario_create_delta_tbl_two():
    df = spark.range(5,11)
    df = df.withColumn("source_file",input_file_name())
    df = df.withColumn("updated", current_timestamp())
    # spark.sql(f"DROP TABLE IF EXISTS project_c.demo.delta2")
    if spark.sql("SHOW TABLES IN main.default LIKE 'users_k'").count() == 0:
        df.write \
            .format("delta")\
            .option("overwriteSchema", "true") \ 
            .option("path", external_location) \
            .saveAsTable("main.default.users_k")
        spark.sql("COMMENT ON TABLE main.default.users_k IS 'This table contains user data for analysis.'")
    else:
        print("Table already exists")
        df.write \
            .format("delta") \
            .mode('append') \
            .save(external_location)
    display(df)

scenario_create_delta_tbl_two()

scenario_create_delta_tbl_two()
                
