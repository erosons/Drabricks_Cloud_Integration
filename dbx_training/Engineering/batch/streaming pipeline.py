from pyspark import pipelines as dp
from pyspark.sql.functions import col


# Please edit the sample below


@dp.table
def streaming_pipeline():
    """
    Reads the raw sample orders JSON data as a streaming source.
    """
    path = "/databricks-datasets/retail-org/sales_orders/"

    schema = """
        customer_name STRING,
        order_number STRING
    """

    return (
        spark.readStream.schema(schema)
            .format("json")
            .option("header", "true")
            .load(path)
            .select(
                col("customer_name"),
                col("order_number"),
            )
    )