# Key Differences:

#     Storage Level: Disk Cache stores the data on disk, while Spark Cache stores the data in memory.
#     Performance: Spark Cache is faster for iterative operations due to in-memory storage. Disk Cache is useful for handling large datasets that do not fit into memory.
#     Use Cases: Use Spark Cache for smaller datasets or when quick access is needed. Use Disk Cache for larger datasets or when memory is a constraint.


# Disk Cache (Tachyon Cache):

# Disk Cache allows you to store the DataFrame on disk. This is useful when you have a 
# large dataset that doesn't fit into memory.
# Import necessary libraries (use Delta Cached Accelerated Compute)
from pyspark.sql import SparkSession

# Initialize Spark Session
spark = SparkSession.builder \
    .appName("DiskCacheExample") \
    .getOrCreate()

# Load data into DataFrame
data = spark.read.csv("/path/to/large_dataset.csv", header=True, inferSchema=True)

# Cache the DataFrame to Disk
data.persist(pyspark.StorageLevel.DISK_ONLY)

# Perform some transformations and actions
transformed_data = data.filter(data["column"] > 0)
result = transformed_data.groupBy("column").count().collect()

# Show results
print(result)

# Stop Spark Session
spark.stop()




# Spark Cache (In-Memory):

# Spark Cache allows you to store the DataFrame in memory. 
# This is faster than Disk Cache for iterative operations.
#Example: Training machine learning models that require multiple passes over the same dataset.

# Import necessary libraries  (use Delta Cached Accelerated Compute)
from pyspark.sql import SparkSession

# Initialize Spark Session
spark = SparkSession.builder \
    .appName("DiskCacheExample") \
    .getOrCreate()

# Load data into DataFrame
data = spark.read.csv("/path/to/large_dataset.csv", header=True, inferSchema=True)

# Cache the DataFrame to Disk
data.persist(pyspark.StorageLevel.DISK_ONLY)

# Perform some transformations and actions
transformed_data = data.filter(data["column"] > 0)
result = transformed_data.groupBy("column").count().collect()

# Show results
print(result)

# Stop Spark Session
spark.stop()

