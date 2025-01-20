# COPY INTO 

# provides SQL engineers an idempotent option to incrementally ingest data from external systems.

# Note that this operation does have some expectations:

#     Data schema should be consistent
#     Duplicate records should try to be excluded or handled downstream

# This operation is potentially much cheaper than full table scans for data that grows predictably.
#######################################
#Load paruquet to an external location
#######################################
from pyspark.sql.types import IntegerType

df = spark.read.table("main.default.sample_superstore_in")
df = df.where(col("Profit") < 100) \
       .withColumn("ShipDate", date_format(col("ShipDate"), "yyyy-MM-dd").cast("date")) \
       .withColumn("RowID", col("RowID").cast("integer")) \
       .select(col("RowID").alias("id"),col("OrderID").alias("name"),col("ShipDate").alias("date"))\
       .write.mode("overwrite") \
       .format("parquet") \
       .save(external_location)


#######################################
#IDEMPOTENT INGESTION WITH COPY INTO
#######################################

%python
from pyspark.sql.functions import *

external_location = spark.sql('describe external location `marketingdata_ingestion`').first()['url'] + '/ingest7'

def scenario_create_delta_tbl_two():
    if spark.sql("SHOW TABLES IN main.default LIKE 'users_incremental_load'").count() == 0:
       spark.sql(f"""CREATE TABLE IF NOT EXISTS main.default.users_incremental_load (
           id INT,name STRING,date DATE)
                 USING DELTA;""")
       spark.sql("COMMENT ON TABLE main.default.users_incremental_load IS 'This table contains user data for analysis.'")
    else:
        # Load data incrementally into the Delta table
        spark.sql(f"""COPY INTO main.default.users_incremental_load
        FROM '{external_location}'
        FILEFORMAT = PARQUET;""")

scenario_create_delta_tbl_two()