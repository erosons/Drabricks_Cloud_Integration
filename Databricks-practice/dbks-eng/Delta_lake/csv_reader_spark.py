# Set the Spark Connect connection string in DatabricksSession.builder.remote.
# comes with pysaprk.sql
from databricks.connect import DatabricksSession
from pyspark.sql.functions import sha2, concat_ws
import pandas as pd
from pyspark.sql import SparkSession, Row
from pyspark.sql.types import (StructField, StructType,
                              ShortType, IntegerType, StringType, FloatType, BooleanType,ArrayType,MapType)
import os
from pprint import pprint
import json
from jsonschema import validate



WORKSPACE_URL: str = os.getenv("databricks_workspaceURL")
print(WORKSPACE_URL)
CLUSTER_ID: str = os.getenv("clusterID")
_token = os.getenv("PAT")



# Option 1:Working or parameters are fulled from the dbconfig #
spark = DatabricksSession.builder.clusterId(CLUSTER_ID).getOrCreate()

# Define the schema
schema = StructType([
    StructField("student_id", IntegerType(), nullable=False),
    StructField("student_first_name", StringType(), nullable=True),
    StructField("student_last_name", StringType(), nullable=True),
    StructField("student_email", StringType(), nullable=True),
    StructField("student_gender", StringType(), nullable=True),
    StructField("student_phone_numbers", ArrayType(StringType(), containsNull=True), nullable=True),
    StructField("student_address", MapType(StringType(), StringType(), valueContainsNull=True), nullable=True),
    StructField("CurrentFlag", StringType(), nullable=True),
    StructField("start_date", StringType(), nullable=True),
    StructField("end_date", StringType(), nullable=True)
])

## Conversion of serialized json string
def student_3():
   file_path = '/home/samson/Desktop/my_sandbox_new/Databricks/Delta_lake/SCD.json'

# Opening JSON file and loading the data into a variable
   with open(file_path, 'r') as file:
        file_ouput = json.load(file)
        # Validate JSON data against the schema
        # try:
        #     validate(instance=file_ouput , schema=file_path)
        #     print("JSON data is valid.")
        # except jsonschema.exceptions.ValidationError as ve:
        #     print("JSON data is invalid.")
        #     print("Validation Error: ", ve)
        #     print(file_ouput)
        pprint(file_ouput["students"])
        l = [Row(**x) for x in file_ouput["students"]]
        print(l)
        df = spark.createDataFrame(l,schema=schema)
        return df.show()
   
# Opening JSON file and loading the data into a variable
   with open(file_path, 'r') as file:
        file_ouput = json.load(file)

def student_3():
    students2_str = """{"students": [{"student_id":4,"student_first_name":"Elyse","student_last_name":"Addionisio","student_email":"eaddionisio3@berkeley.edu","student_gender":"Polygender","student_phone_numbers":["7347984926","3364474838","7136381150"],"student_address":{"street":"77 Sugar Alley","city":"Atlanta","state":"Georgia","postal_code":"31132"}},{"student_id":5,"student_first_name":"Lilian","student_last_name":"Warret","student_email":"lwarret4@nsw.gov.au","student_gender":"Male","student_phone_numbers":["5031246553","6151432197","2152754201"],"student_address":{"street":"82540 Summer Ridge Point","city":"Sioux Falls","state":"South Dakota","postal_code":"57193"}},{"student_id":6,"student_first_name":"Tate","student_last_name":"Swyne","student_email":"tswyne5@hud.gov","student_gender":"Agender","student_phone_numbers":["2021437429","8507115330","3047568052","7818031186","6072847440"],"student_address":{"street":"23 Sommers Parkway","city":"El Paso","state":"Texas","postal_code":"88569"}},{"student_id":7,"student_first_name":"Ichabod","student_last_name":"Moring","student_email":"imoring6@un.org","student_gender":"Female","student_phone_numbers":["7147001301","9895085931"],"student_address":{"street":"584 Reindahl Way","city":"Denver","state":"Colorado","postal_code":"80228"}},{"student_id":8,"student_first_name":"Ariel","student_last_name":"Howler","student_email":"ahowler7@tinypic.com","student_gender":"Agender","student_phone_numbers":"null","student_address":{"street":"null","city":"null","state":"null","postal_code":"null"}},{"student_id":9,"student_first_name":"Octavia","student_last_name":"Stenner","student_email":"ostenner8@networksolutions.com","student_gender":"Bigender","student_phone_numbers":"null","student_address":{"street":"null","city":"null","state":"null","postal_code":"null"}},{"student_id":10,"student_first_name":"Ronda","student_last_name":"Stean","student_email":"rstean9@xrea.com","student_gender":"Genderfluid","student_phone_numbers":"null","student_address":{"street":"null","city":"null","state":"null","postal_code":"null"}}]}"""
    file_ouput = json.loads(students2_str)
    l = [Row(**x) for x in file_ouput["students"]]
    df = spark.createDataFrame(l)
    return df


def student_1():
   """
   When you are reading a file from out of spark env,use CreatedataFrame
   """
   file_path = os.path.expanduser('/home/samson/Desktop/my_sandbox_new/Databricks-project/sample-case_1.csv')
   df =pd.read_csv(file_path)
   d=df.to_dict(orient='records')
   df = spark.createDataFrame(d)
   df = df.withColumn("record_hash", sha2(concat_ws("||", *df.columns), 256))
   return df

def student_2():
   df = spark.read.format('csv') \
         .option('header','true') \
         .option("inferSchema", "true")\
        .load('dbfs:/raw/sample-case_2.csv')
   return df


def student_append():
   """
   When you are reading a file from out of spark env,use CreatedataFrame
   """
   file_path = os.path.expanduser('/home/samson/Desktop/my_sandbox_new/Databricks-project/sample-case_5.csv')
   df =pd.read_csv(file_path)
   d=df.to_dict(orient='records')
   df = spark.createDataFrame(d)
   df = df.withColumn("record_hash", sha2(concat_ws("||", *df.columns), 256))
   return df

if __name__ == "__main__":
    student_3()