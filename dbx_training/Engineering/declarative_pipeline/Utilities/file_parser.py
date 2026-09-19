# --------- HELPERS ----------
from pyspark.sql import functions as F

class Transformer:

    @staticmethod
    def quarantine_windowing(key_cols, order_cols=None):
        """
        key_cols: tuple/list of columns to identify duplicates, e.g. ("CustomerID","OrderDate")
        order_cols: tuple/list of columns for stable ordering; earliest wins.
        """
        if order_cols is None:
            order_cols = []
        return Window.partitionBy(*[F.col(c) for c in key_cols]).orderBy(*[F.col(c) for c in order_cols])

    @staticmethod
    def parse(df):
        return (
            df
            .withColumn("processed_timestamp", F.current_timestamp())
            .withColumn("source_system", F.lit("ADLS"))  # or F.lit("adls")
            .withColumn("Profit",   F.col("Profit").cast("float"))
            .withColumn("Sales",    F.col("Sales").cast("float"))
            .withColumn("Quantity", F.col("Quantity").cast("int"))
        )