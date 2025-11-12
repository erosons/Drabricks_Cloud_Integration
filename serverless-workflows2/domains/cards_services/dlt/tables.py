# domains/<domain>/dp/tables.py
from pyspark import pipelines as dp 
from pyspark.sql.functions import col, current_timestamp, input_file_name, sha2, concat_ws
from utils.warehouses import ensure_sql_warehouse

def get_conf(key, default=None):
    try:
        return spark.conf.get(key)
    except Exception:
        return default

domain:str = get_conf("domain")    

# Convenience to read config passed via pipeline.yml
@dp.view
def _cfg():
    return spark.createDataFrame([{
        "ingest_path": spark.conf.get("ingest_path"),
        "target_catalog": spark.conf.get("target_catalog"),
        "target_schema": spark.conf.get("target_schema"),
    }])

@dp.table(
    name=f"{domain}_seal",
    comment="Raw landed files with metadata",
    table_properties={"delta.enableChangeDataFeed": "true"}
)
@dp.expect("has_payload", "payload IS NOT NULL")
def bronze_raw():
    cfg = dp.read("_cfg").first().asDict()
    df = (
        spark.readStream.format("cloudFiles")
        .option("cloudFiles.format", "json")      # change to csv/parquet as needed
        .option("cloudFiles.inferColumnTypes","true")
        .load(cfg["ingest_path"])
    )
    return (
        df.withColumn("_ingest_time", current_timestamp())
          .withColumn("_source_file", input_file_name())
    )

@dp.table(
    name=f"{domain}_trusted",
    comment="Conformed, deduped records with standard types",
    table_properties={"delta.autoOptimize.optimizeWrite": "true"}
)
@dp.expect_or_drop("id_present", "id IS NOT NULL")
def silver_clean():
    b = dp.read_stream("bronze_raw")
    # example light transform/dedup
    return (
        b.dropDuplicates(["id"])
         .withColumn("_record_hash", sha2(concat_ws("||", *b.columns), 256))
    )

@dp.table(
    name=f"{domain}_refined",
    comment="Gold model for BI/serving",
    table_properties={"delta.autoOptimize.autoCompact": "true"}
)
def gold_serving():
    s = dp.read("silver_clean")
    # sample star-schema friendly projection
    return (
        s.select(
            "id", "payload", "_ingest_time", "_source_file", "_record_hash"
        )
    )
