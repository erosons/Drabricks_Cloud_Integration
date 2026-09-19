import dlt
from pyspark.sql import SparkSession

# Assuming standard_transform is defined somewhere
def standard_transform(df):
    return df.selectExpr("trim(lower(id)) as id")

# Function to create a DLT table function
def create_dlt_table(source_path, table_name):
    @dlt.table(
        name=table_name,
        comment=f"Table generated from {source_path}"
    )
    def inner_table():
        df = spark.range(1,10)
        return standard_transform(df)
    return inner_table

# Dictionary of regions and their data paths
regions = {
    "north": "north",
    "south": "south",
    "east": "east",
    "west": "west"
}

# Generate a DLT table for each region using a factory function
for region, path in regions.items():
    create_dlt_table(path, f"{region}_data")()