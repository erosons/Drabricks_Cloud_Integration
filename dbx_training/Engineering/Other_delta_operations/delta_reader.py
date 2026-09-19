

def delta_read_student_2():
    # Executing read 
    df = spark.read \
    .format("delta") \
    .load("s3://extertables-loc/project1/")
    #print(df.columns)
    df.toDF(*df.columns).show()
