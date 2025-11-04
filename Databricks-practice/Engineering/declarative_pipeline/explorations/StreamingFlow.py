# Databricks notebook source
# MAGIC %md
# MAGIC ### https://docs.databricks.com/aws/en/ldp/concepts

# COMMAND ----------

# @AUTOCDC wit Fivetran or lakeflow connector with SCD2
# dlt.create_streaming_table(name="silver_cdc", table_properties={"quality":"silver"})

# from pyspark.sql.functions import col, expr
# dlt.apply_changes(
#     target                 = "silver_cdc",
#     source                 = "bronze_events",   # your CDC bronze
#     keys                   = ["id"],
#     sequence_by            = col("_commit_ts"), # or your ordering column
#     apply_as_deletes       = expr("op = 'DELETE'"),
#     except_column_list     = ["op", "_commit_ts", "_valid_from", "_valid_to"],
#     track_history_columns  = ["_commit_ts"]
# )


# COMMAND ----------

# # Optional: materialize the invalid rows (duplicates) as a named quarantine table
# @dp.table(
#     name="bronze_incremental_quarantine",
#     comment="Duplicate rows quarantined from bronze via expectation failures",
#     table_properties={"quality": "bronze"}
# )
# def bronze_incremental_quarantine():
#     # DLT exposes a standard failures view for each expectation:
#     # <table_name>_expectations_<expectation_name>_failures
#     return (
#         dp.read("bronze_incremental_table_expectations_valid_row_failures")
#         .withColumn("quarantine_reason", F.lit("duplicate detected by window"))
#     )

