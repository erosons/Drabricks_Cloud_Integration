-- Description: This script is used to create a temp view
-- in databricks that is used in the current session of notebook/jobs/sql query only
CREATE  OR REPLACE TEMP VIEW temp_view
AS 
SELECT * FROM city_bike.default.marketingdata_silver


-- Equivalent to the above code snippet, the following code snippet

df.createOrReplaceTempView("json_view")


-- Another way to create a temp view is by using the below code snippet--deprecated
df = spark.read.json('abfss|s3:/').registerTempTable("json_view")


