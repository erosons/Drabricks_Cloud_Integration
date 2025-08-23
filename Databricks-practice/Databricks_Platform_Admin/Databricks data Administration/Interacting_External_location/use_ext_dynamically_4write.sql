%python --This will return a named Tuple
external_location =spark.sql('describe external location `marketingdata_ingestion`').first()['url']+'/silver'
spark.conf.set("datastore.silver.url", external_location)

%python --Dynamically write to a storage_path
df = spark.range(100)
df.write.format("delta").mode("overwrite").save(external_location)

-- List the external_storage path USING the params define in the spark SET imn notebook
LIST '${datastore.silver.url}'

--Generate SQL 
SELECT "LIST '${datastore.silver.url}'"  as Query

--GRANT PERMISSION
GRANT READ FILES ON EXTERNAL LOCATION '${datastore.silver.url}' TO `poc@hotmail.onmicrosoft.com`;

--CREATE EXTERNAL TABLE

%sql
CREATE TABLE IF NOT EXISTS city_bike.default.marketingdata_silver
USING PARQUET|DELTA|CSV
OPTION (
       key = value, 
       key = value ..,
       header = "true",
       delimiter = "|")
LOCATION '${datastore.silver.url}'

-------------------------------------
--- Python version of the above code
--------------------------------------

%python
spark.sql(f"""
CREATE TABLE IF NOT EXISTS sales_csv
  (order_id LONG, email STRING, transactions_timestamp LONG, total_item_quantity INTEGER, purchase_revenue_in_usd DOUBLE, unique_items INTEGER, items STRING)
USING CSV
OPTIONS (
  header = "true",
  delimiter = "|"
)
LOCATION "{DA.paths.sales_csv}"
""")

------------------------------
--MANGED EXTERNAL TABLES
------------------------------


%python --This will return a named Tuple
external_location=spark.sql(
    'describe external location `marketingdata_ingestion`').first()['url']+'/silver'

spark.conf.\
set(
    "datastore.silver.url", external_location
    )

%sql
-- This can be done at the CATALOG LEVEL SCHEMA LEVEL
-- This is a way to override the managed table with an external table and stores metadata in the external location
CREATE Schema
IF NOT EXISTS city_bike.override_managed
MANAGED LOCATION '${datastore.silver.url2}'