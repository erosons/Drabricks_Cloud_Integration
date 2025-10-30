from delta.tables import (DataFrame,
                          DeltaTable,
                          DeltaTableBuilder,
                          DeltaOptimizeBuilder)
from pyspark.sql.functions import col,lit
from delta_reader import spark

# Call the Delta table and return a delta Object
# This function updates the functions such
 #  CRUD - Update, append/insert/delete, merge


delta_table = DeltaTable.forPath(spark, "s3://extertables-loc/project1/")
print(f'returns delta object ,{delta_table}')
print(f'this delta object is can used just a regular dataframe')
#delta_table.toDF().show()
delta_table.toDF().printSchema()

## Performing an update Operations
# - conditions
# - set
delta_table.update(
   
   condition = col("RowID") == 4,
        set = { "ShipMode": lit("FirstClass") } 
        )
delta_table.toDF().show()