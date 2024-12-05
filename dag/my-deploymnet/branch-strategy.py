# Databricks notebook source
dbutils.widgets.text("yearValue", "2015")

# COMMAND ----------

# MAGIC %sql
# MAGIC SELECT * FROM main.default.sample_superstore_in
# MAGIC where year(OrderDate) ==:yearValue
