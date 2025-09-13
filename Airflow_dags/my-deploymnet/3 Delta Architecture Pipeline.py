# Databricks notebook source
# MAGIC %md-sandbox
# MAGIC 
# MAGIC <div style="text-align: center; line-height: 0; padding-top: 9px;">
# MAGIC   <img src="https://databricks.com/wp-content/uploads/2018/03/db-academy-rgb-1200px.png" alt="Databricks Learning" style="width: 600px">
# MAGIC </div>

# COMMAND ----------

# MAGIC %md
# MAGIC # Overview
# MAGIC 
# MAGIC This notebook constitutes a Delta Live Tables implementation of *Building automating a Data Pipeline*. This notebook is intended to be run as a DLT pipeline, not interactively.
# MAGIC 
# MAGIC The result will consist of the following collection of tables:
# MAGIC * A bronze table that ingests raw data
# MAGIC * A silver table representing the bronze table with a cleaned up schema and basic standardization of the column values
# MAGIC * A couple gold tables performing various aggregations against the silver table
# MAGIC 
# MAGIC The dataset is provided as part of the collection of Databricks sample datasets and contains information related to movie productions.

# COMMAND ----------

import dlt
from pyspark.sql.functions import *
from pyspark.sql.types import *

@dlt.table(
  comment="The raw movie dataset, ingested from /databricks-datasets."
)
def bronze_movies():
  return (spark.read.format("csv")
          .option("header", "true")
          .option("sep", ",")
          .load("/databricks-datasets/Rdatasets/data-001/csv/ggplot2/movies.csv"))

@dlt.table(
  comment="Cleaned up schema and imposed some standards on the data."
)
@dlt.expect("valid_mpaa_rating", "mpaa IN ('NR','G','PG','PG-13','R','NC-17')")
def silver_movies():
  return (
    dlt.read("bronze_movies")
      .withColumnRenamed("_c0", "idx")
      .withColumn("year", expr("CAST(year AS INT)"))
      .withColumn("length", expr("CAST(length AS INT)"))
      .withColumn("budget", expr("CASE WHEN budget = 'NA' THEN 0 ELSE CAST(budget AS INT) END"))
      .withColumn("rating", expr("CAST(rating AS DOUBLE)"))
      .withColumn("votes", expr("CAST(votes AS INT)"))
      .withColumn("mpaa", expr("CASE WHEN mpaa is null THEN 'NR' ELSE mpaa END"))
      .withColumn("Action", expr("CAST(Action AS BOOLEAN)"))
      .withColumn("Comedy", expr("CAST(Comedy AS BOOLEAN)"))
      .withColumn("Drama", expr("CAST(Drama AS BOOLEAN)"))
      .withColumn("Documentary", expr("CAST(Documentary AS BOOLEAN)"))
      .withColumn("Romance", expr("CAST(Romance AS BOOLEAN)"))
      .withColumn("Short", expr("CAST(Short AS BOOLEAN)"))
      .select("year", "title", "length", "budget", "rating", "votes", "mpaa", "Action", "Drama", "Documentary", "Romance", "Short")
  )

@dlt.table(
  comment="Average production budget year over year."
)
def gold_average_budget_by_year():
  return (
    dlt.read("silver_movies")
      .filter(expr("budget > 0"))
      .groupBy("year")
      .agg(avg("budget").alias("average_budget"))
      .orderBy("year")
      .select("year", "average_budget")
  )

@dlt.table(
  comment="Average production count year over year."
)
def gold_movies_made_by_year():
  return (
    dlt.read("silver_movies")
      .groupBy("year")
      .agg(sum("year").alias("movies_made"))
      .orderBy("year")
      .select("year", "movies_made")
  )

# COMMAND ----------

# MAGIC %md-sandbox
# MAGIC &copy; 2022 Databricks, Inc. All rights reserved.<br/>
# MAGIC Apache, Apache Spark, Spark and the Spark logo are trademarks of the <a href="https://www.apache.org/">Apache Software Foundation</a>.<br/>
# MAGIC <br/>
# MAGIC <a href="https://databricks.com/privacy-policy">Privacy Policy</a> | <a href="https://databricks.com/terms-of-use">Terms of Use</a> | <a href="https://help.databricks.com/">Support</a>