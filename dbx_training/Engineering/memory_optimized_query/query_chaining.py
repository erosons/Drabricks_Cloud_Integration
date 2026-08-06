from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when, count

# Start Spark session
spark = SparkSession.builder.appName("Optimization Example").getOrCreate()

# Sample data
data = [("John Doe", 23), ("Jane Smith", 29), ("Mary Johnson", 65), ("James Brown", 60)]
columns = ["name", "age"]

# Creating DataFrame
df = spark.createDataFrame(data, schema=columns)

# Using DataFrame API with DSL expressions
filtered_df = df.filter(col("age") > 25) \
                .withColumn("senior", when(col("age") >= 60, True).otherwise(False)) \
                .groupBy("senior") \
                .agg(count("name").alias("count"))

# Show the result
filtered_df.show()
