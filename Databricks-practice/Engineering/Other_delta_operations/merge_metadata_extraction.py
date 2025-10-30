# Describe History on Delta Lake , exposes the history of all the operations that have been performed on the Delta table.
#     delta_table.history().show()

#Extract records that where updated or inserted in the Delta Lake table

%python
from pyspark.sql.functions import col

dfs = spark.sql('describe history purchase_dates')
df= (dfs.select('*',col('OperationMetrics.numOutputRows'))
   .where(col('timestamp') == dfs.agg(max(col('timestamp'))).collect()[0][0])
).display()