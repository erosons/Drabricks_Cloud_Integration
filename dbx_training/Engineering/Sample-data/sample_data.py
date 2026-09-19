import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from pyspark.sql import Row
from pyspark.sql.types import StructField, StructType, IntegerType, StringType, TimestampType
# Number of samples
num_samples = 10

# Generate random data
device_id = np.random.randint(10, 50, num_samples)
name=np.random.choice(["Nicholas Spears", "Lynn Russell", "Samuel Hughes"], num_samples)
time = [datetime.now() - timedelta(minutes=15 * i) for i in range(num_samples)]
heartrate =np.random.uniform(50, 100, num_samples)
data = [{"device_id": device_id[i], "name": name[i], "time": time[i], "heartrate": heartrate[i]} for i in range(num_samples)]

newDataschema=[StructField('device_id',IntegerType(),True),
               StructField('name',StringType(),True),
               StructField('time',TimestampType(),True),
               StructField('heartrate',IntegerType(),True)
                ]

# Create a DataFrame
df = spark.createDataFrame([Row(**data) for data in data],schema=StructType(newDataschema))
df.createOrReplaceTempView("heart_rate")
#df = spark.createDataFrame(data,schema=StructType(newDataschema))
mySQL = """
       SELECT * FROM heart_rate
 """

spark.sql(mySQL).display()