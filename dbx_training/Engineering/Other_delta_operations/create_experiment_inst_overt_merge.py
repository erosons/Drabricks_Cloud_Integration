# The idea is to create a delta table from the experiment instance 
# where if the number of records incoming is less  iterate and perform insert overwrite,
# but if the number of records is more than the existing records then perform merge operation.

%python
from pyspark.sql.functions import *
from pyspark.sql.types import StructType, StructField, IntegerType, StringType, DateType
from delta.tables import DeltaTable

# Define the schema
schema = StructType([
    StructField("id", IntegerType(), True),
    StructField("name", StringType(), True),
    StructField("date", StringType(), True)
])

# simulated Initial data
start_date = datetime.strptime('2023-01-01', '%Y-%m-%d')
data = [(i, "Alice"+str(i), (start_date + timedelta(days=i)).strftime('%Y-%m-%d') ) for i in range(10) ] 
df = spark.createDataFrame(data, schema)

# Convert the date column to date type
df = df.withColumn("date", to_date(col("date"), "yyyy-MM-dd"))

# Define the external location
external_location = spark.sql('describe external location `marketingdata_ingestion`').first()['url'] + '/ingest6'

def scenario_create_delta_tbl_two():
    # Check if the table 'users_k' exists in the 'main.default' schema
    table_exists = spark.sql("SHOW TABLES IN main.default LIKE 'users_experiment'").count() > 0
    
    if not table_exists:
        # If the table does not exist, create it and partition by date
        print("performing CRAS")
        df.write \
            .format("delta") \
            .partitionBy("date") \
            .option("overwriteSchema", "true") \
            .option("path", external_location) \
            .saveAsTable("main.default.users_experiment")
        spark.sql("COMMENT ON TABLE main.default.users_experiment IS 'This table contains user data for analysis.'")
    else:
        # If the table exists, get the count of existing records
        existing_count = spark.sql("SELECT COUNT(*) FROM main.default.users_experiment").collect()[0][0]
        incoming_count = df.count()
        
        if incoming_count < existing_count:
            # Perform INSERT OVERWRITE for the partition if incoming records are less
            print("performing insert overwrite")
            dates = [row['date'] for row in df.select('date').distinct().collect()]
            date_predicate = "date IN ({})".format(", ".join(["'{}'".format(date) for date in dates]))
            df.write \
                .format("delta") \
                .mode("overwrite") \
                .option("replaceWhere", date_predicate) \
                .saveAsTable("main.default.users_experiment")
        else:
            # Perform MERGE operation if incoming records are more
            print("performing merge")
            delta_table = DeltaTable.forName(spark, "main.default.users_experiment")
            delta_table.alias("tgt").merge(
                df.alias("src"),
                "tgt.id = src.id AND tgt.date = src.date"
            ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
    
    display(df)

scenario_create_delta_tbl_two()
