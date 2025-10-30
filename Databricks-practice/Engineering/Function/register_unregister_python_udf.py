# A custom column transformation function

# - Can’t be optimized by Catalyst Optimizer
# - Function is serialized and sent to executors
# - Row data is deserialized from Spark's native binary format to pass to the UDF, and the results are serialized back into Spark's native format
# - For Python UDFs, additional interprocess communication overhead between the executor and a Python interpreter running on each worker node

%python 
def price_discount_udf(col:str,price:int,discount:int):
  match col:
      case "Standard Queen Mattress":
          return 'This is my default mattress'
      case "Premium Queen Mattress":
         return "This is my favorite mattress"
  if price > 100: return "I'd wait until the "+ col + " is on sale for $"+str(round(price * 0.8, 0))




# Apply the UDF to be used in the DataFrame|# Register the UDF with Spark into a persistent function that can be used in SQL queries across all clusters
register_functioned = udf(price_discount_udf) | registered_function = spark.udf.register("register_function", price_discount_udf)
# This serializes the function and sends it to the executors


# FOR SQL use the UDF alias for the price_discount
  SELECT register_function(name,price,0.8) as price_discount FROM item_lookup

# Apply the UDF to a DataFrame
from pyspark.sql.functions import lit, col

df = spark.sql('SELECT * FROM item_lookup')
df = df.select(
    '*',
    registered_function(col('name'),col('price'),lit(0.8)).alias('price_discount')
)
display(df)



########################################################
# Using UDF decorator and no need to register the UDF
##########################################################

# using the decorator to register the UDF with Spark, the function is registered
#  as a persistent function that can be used in SQL queries across all clusters. you will longer be a to call the func locally.

@udf('string')  
# String is the return type of the UDF
def price_discount_udf(col:str,price:int,discount:int)->str:
  match col:
      case "Standard Queen Mattress":
          return 'This is my default mattress'
      case "Premium Queen Mattress":
         return "This is my favorite mattress"
  if price > 100: return "I'd wait until the "+ col + " is on sale for $"+str(round(price * 0.8, 0))

# Usage of the UDF
# Apply the UDF to a DataFrame
from pyspark.sql.functions import lit, col

df = spark.sql('SELECT * FROM item_lookup')
df = df.select(
    '*',
    price_discount_udf(col('name'),col('price'),lit(0.8)).alias('price_discount')
)
display(df)



@pandas UDF
NOTE: Only use when you are dealing Series of data
# Is a decorator in PySpark used to define Pandas User Defined Functions (UDFs). 
# These UDFs allow you to leverage the power of Pandas within Spark, 
# enabling you to write vectorized operations on DataFrames, which can significantly improve performance compared to row-at-a-time UDFs.

# Benefits of using Pandas UDFs:

#     Performance:
#     Pandas UDFs utilize Apache Arrow to transfer data between Spark and Pandas, leading to faster data processing compared to traditional UDFs.
#     Expressive Power:
#     You can use the rich Pandas API within your UDFs, allowing you to perform complex transformations and calculations easily.

import pandas as pd
from pyspark.sql.functions import pandas_udf

@pandas_udf('double', PandasUDFType.SCALAR_ITER)
def add_one(s: pd.Series) -> pd.Series:
    return s + 1

df = spark.createDataFrame([(1,), (2,), (3,)], ['value'])
df.withColumn('value_plus_one', add_one('value')).show()