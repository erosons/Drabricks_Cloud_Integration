## Object of DeltaFormat is for ACID opertaions
from csv_reader_spark import  student_2,student_1,student_append

def delta_write():
    df = student_1()
    df.write \
    .format("delta") \
    .option("overwriteSchema", "true")\
    .save("s3://extertables-loc/project1/")
    #.save("dbfs:/deltaformat/delta_1")
    df.show()

def delta_append():
    df = student_append()
    df.write \
    .format("delta") \
    .mode('append')\
    .save("s3://extertables-loc/project1/")
    #.save("dbfs:/deltaformat/delta_1")
    df.show()

def repartition():
    """
    redistribute data across partitions in a DataFrame, 
    allowing for more even data distribution,
    """
    df = student_append()
    df.write \
    .option("dataChange","false") \
    .format("delta") \
    .mode('overwrite')\
    .save("s3://extertables-loc/project1/")
    #.save("dbfs:/deltaformat/delta_1")
    df.show()
        
def delta_to_Table():        
    df.write \
        .format("delta") \
        .options(**bucketpath) \
        .option("overwriteSchema", "true")\
        .saveAsTable("{}.{}".format(schema=schema,bucketpath=deltalake_bucketpath))