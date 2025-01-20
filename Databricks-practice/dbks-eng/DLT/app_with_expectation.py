import dlt
from pyspark.sql.functions import *

# Define Bronze Layer
@dlt.table(
    comment="Raw data ingestion from test_catalog.saleslt.customer",
    table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true",
        'delta.deletedFileretentionDuration' : "30 days"
        }
)
def bronze_customer():
    file_path = spark.conf.get("spark.sql.inputPath")
    stream_df = spark.readStream \
                .format('cloudFiles') \
                .option('cloudFiles.format','json') \
                .option('cloudFiles.schemaLocation', file_path) \
                .option("path",'s3://acm-test-bucket/sanbox2/') \
                .option("maxFilesPerTrigger", 1) \
                .load()

    return (
        stream_df.sql("SELECT *, current_date() as loaddate FROM test_catalog.saleslt.customer")
        .withColumnRenamed("customerid", "bronze_customerid")
    )




# Define Silver Layer with data cleaning and deduplication
@dlt.table(
    comment="Cleansed and deduplicated data from Bronze layer",
      table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true",
        'delta.deletedFileretentionDuration' : "30 days"
        }
)
@dlt.expect("valid timestamp", col("loaddate") > '2012-01-01')
@dlt.expect_or_drop("columnsdrop", "FirstName IS NOT NULL AND LastName IS NOT NULL")
@dlt.expect_or_fail("emailaddress", col("emailaddress").isNotNull())
@dlt.expect_flag("emailaddress", col("emailaddress").isNotNull())
def silver_customer():

    bronze_df = dlt.read("bronze_customer")
    return (
        bronze_df.dropDuplicates(["bronze_customerid"])
        .filter(col("emailaddress").isNotNull())  # Example of data quality check
        .selectExpr("bronze_customerid as customerid", "*")
    )



# Define Gold Layer with aggregations or additional enrichment
@dlt.table(
    comment="Aggregated and enriched data from Silver layer",
    table_properties={
        "delta.autoOptimize.optimizeWrite": "true",
        "delta.autoOptimize.autoCompact": "true",
        'delta.deletedFileretentionDuration' : "30 days"
        }
)
def gold_customer():
    silver_df = dlt.read("silver_customer")
    return (
        silver_df.groupBy("loaddate")
        .count()
        .withColumnRenamed("count", "customer_count")
    ) 