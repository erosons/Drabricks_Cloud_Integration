# Databricks notebook source
from pyspark.sql.functions import *
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .appName("OptimizationExample") \
    .config("spark.dynamicAllocation.enabled", "true") \
    .config("spark.dynamicAllocation.minExecutors", "1") \
    .config("spark.dynamicAllocation.maxExecutors", "3") \
    .config("spark.shuffle.service.enabled", "true") \
    .config("spark.sql.files.maxPartitionBytes", "67108864") \
    .config("spark.sql.shuffle.partitions", "200") \
    .config("spark.sql.adaptive.enabled", "true") \
    .config("spark.sql.adaptive.advisoryPartitionSizeInBytes", "67108864") \
    .config("spark.sql.adaptive.coalescePartitions.enabled", "true") \
    .config("spark.sql.adaptive.skewJoin.skewedPartitionThresholdInBytes","67108864")\
    .config("spark.sql.autoBroadcastJoin.enabled", "-1") \
    .config("spark.sql.join.preferSortMergeJoin", "true")\
    .getOrCreate()

dfs = spark.read.format('json').option('inferSchema', 'true').option('header','true').load('/mnt/ghactivity/')
dfk = spark.read.format('json').option('inferSchema', 'true').option('header','true').load('/mnt/ghactivity/')

# Dropping the tables
spark.sql("DROP TABLE IF EXISTS course_project.city_bike.sampletbl1")
spark.sql("DROP TABLE IF EXISTS course_project.city_bike.sampletbl2")

# Writing and Bucketing presorting the merging keys
dfs.write.format("delta").option("overwrite","true").partitionBy("id").saveAsTable('course_project.city_bike.SampleTbl1')
dfk.write.format("delta").option("overwrite","true").partitionBy("id").saveAsTable('course_project.city_bike.SampleTbl2')

# ZOrdering the Tables
spark.sql("OPTIMIZE course_project.city_bike.sampletbl1 ZORDER BY id")
spark.sql("OPTIMIZE course_project.city_bike.sampletbl2 ZORDER BY id")

# Caching the Tables
spark.sql("CACHE TABLE course_project.city_bike.sampletbl1")
spark.sql("CACHE TABLE course_project.city_bike.sampletbl2")

# read table 
tabldf1 = spark.table("SampleTbl1")
tabldf2 = spark.table("SampleTbl2")

joinDf = tabldf1.join(tabldf2, tabldf1.id == tabldf2.id)
# display(joinDf)
