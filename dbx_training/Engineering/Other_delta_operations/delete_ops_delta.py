from delta.tables import (DataFrame,
                          DeltaTable,
                          DeltaTableBuilder,
                          DeltaOptimizeBuilder)
from databricks.connect import DatabricksSession
from pyspark.sql.functions import col,lit,expr
from read_deltaframe import spark

# Call the Delta table and return a delta Object
# This function updates the functions such
 #  CRUD - Update, append/insert/delete, merge
 
delta_table = DeltaTable.forPath(spark, "dbfs:/deltaformat/delta_1") # -> external location
# deltaTable = DeltaTable.forName(spark, "main.default.people_10m") -> in the unity catalog

print(f'returns delta object ,{delta_table}')
print(f'this delta object is can used just a regular dataframe')

#delta_table.toDF().show()
delta_table.toDF().printSchema()

## Performing an update Operations
# - conditions
# - set
# - using help condition -> help(delta_table.delete)

delta_table.delete(
      col("student_id") == 5  # Predicate using Spark SQL
      #expr("student_id") == 4
        )

delta_table.toDF().show()

