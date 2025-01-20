%python
# Returns Files path and Metadata INFORMATION
df = spark.read.format("binaryFile").load('')

# Register the DataFrame as a temporary view
df.createOrReplaceTempView("json_view")

# Query the temporary view using SQL
result = spark.sql("SELECT * FROM json_view")

# Display the result
display(result)