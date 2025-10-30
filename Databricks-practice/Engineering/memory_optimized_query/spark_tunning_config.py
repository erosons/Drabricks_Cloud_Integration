from pyspark.sql import SparkSession
"""
Spark splits the data into partitions based on the spark.sql.files.maxPartitionBytes
configuration. By default, this is set to 128 MB. You can adjust this setting based on
your data size and the memory capacity of your executors.

1. Problem: Data might be unevenly distributed across partitions. Some partitions could be
    significantly larger than others, leading to some nodes in your cluster doing much more
    work than others. This uneven load can cause performance bottlenecks.
    Solution: Repartitioning helps redistribute the data more evenly across all available nodes
              in the cluster. By doing this, you can ensure that each node processes roughly the same 
              amount of data, improving overall job execution time and resource utilization.
2. Increasing Parallelism
    Problem: The default number of partitions might not be optimal for the available cluster resources.
             If there are fewer partitions than the number of available executor cores, some cores might
             remain idle.
    Solution: By increasing the number of partitions, you can increase the level of parallelism. This
              ensures that more executors can be utilized concurrently, speeding up processing.
3. Optimizing for Data Shuffling
    Problem: Certain operations like groupBy, join, or reduceByKey can cause a lot of data to be
            shuffled across the network if the data isn't partitioned optimally beforehand. Shuffling
            is expensive and can significantly slow down processing.
    Solution: Repartitioning the data based on the keys used in these operations (using methods like 
        repartition or partitionBy in Spark) can minimize data shuffling as the data will already be organized
        according to the required keys.
4. Managing Memory Use
    Problem: Large partitions might lead to out-of-memory errors during processing, especially if the
           operations performed on the data are memory-intensive.
    Solution: Repartitioning can help break down large partitions into smaller, more manageable chunks,
            reducing the memory required per task and preventing memory overflow issues.
"""

spark = SparkSession.builder \
    .appName("OptimizationExample") \
    .config("spark.dynamicAllocation.enabled", "true") \
    .config("spark.dynamicAllocation.minExecutors", "1") \
    .config("spark.dynamicAllocation.maxExecutors", "2") \
    .config("spark.shuffle.service.enabled", "true") \
    .config("spark.sql.files.maxPartitionBytes", "67108864") \
    .config("spark.sql.shuffle.partitions", "200") \
    .config("spark.sql.adaptive.enabled", "true") \
    .config("spark.sql.adaptive.advisoryPartitionSizeInBytes", "67108864") \
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
    .config("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes","67108864")\
    .getOrCreate()

df = spark.read.csv("s3a://your-bucket/path/to/data/")
df_repartitioned = df.repartition(200)  # Adjust based on your needs
df_repartitioned.show()


##########################################################
#### Another scenario for Spark read Optiization######
##########################################################
# Overriding the default configuration
spark = SparkSession.builder \
    .appName("OptimizationExample") \
    .config("spark.dynamicAllocation.enabled", "true") \
    .config("spark.dynamicAllocation.minExecutors", "1") \
    .config("spark.dynamicAllocation.maxExecutors", "2") \
    .config("saprk.dynamicAllocation.schedulerBacklogTimeout","1m") \
    .config("saprk.dynamicAllocation.executorIdleTimeout","2m") \
    .config("spark.shuffle.service.enabled", "true") \
    .config("spark.sql.files.maxPartitionBytes", "67108864") \
    .config("spark.sql.shuffle.partitions", "200") \
    .config("spark.sql.adaptive.enabled", "true") \
    .config("spark.sql.adaptive.advisoryPartitionSizeInBytes", "67108864") \
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
    .config("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes","67108864")\
    #https://learn.microsoft.com/en-us/azure/databricks/optimizations/disk-cache#disk-cache-vs-spark-cache
    .config("spark.databricks.io.cache.enabled", "[true | false]") \
    .config("spark.databricks.io.cache.maxDiskUsage 50g ")\
    .config("spark.databricks.io.cache.maxMetaDataCache 1g ")\
    .config("spark.databricks.io.cache.compression.enabled false ")\
    .getOrCreate()

large_table = spark.read.format('csv') \
  .option("header","true") \
  .option('inferSchema','true') \
  .load('/mnt/engineering/SampleSuperstore(in).csv')
display(large_table)

sample_table = spark.read.format('csv') \
  .option("header","true") \
  .option('inferSchema','true') \
  .load('/mnt/engineering/Returns.csv')
display(large_table)

from pyspark.sql.functions import broadcast

# Broadcast the smaller table
optimized_join = large_table.join(broadcast(sample_table), "OrderID", "inner")
num_partitions = optimized_join.rdd.getNumPartitions()
print(f"Number of partitions: {num_partitions}")
