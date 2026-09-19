"""
Unit Tests for Data Transformation Functions

These tests can run locally without a Databricks cluster using PySpark.
"""

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import *
from datetime import datetime


@pytest.fixture(scope="session")
def spark():
    """Create a local Spark session for testing."""
    return SparkSession.builder \
        .master("local[*]") \
        .appName("unit-tests") \
        .config("spark.sql.extensions", "io.delta.sql.DeltaSparkSessionExtension") \
        .config("spark.sql.catalog.spark_catalog", "org.apache.spark.sql.delta.catalog.DeltaCatalog") \
        .getOrCreate()


@pytest.fixture
def sample_bronze_data(spark):
    """Create sample bronze layer data for testing."""
    schema = StructType([
        StructField("id", StringType(), True),
        StructField("event_type", StringType(), True),
        StructField("event_timestamp", TimestampType(), True),
        StructField("payload", StringType(), True),
        StructField("source_system", StringType(), True),
        StructField("_ingestion_timestamp", TimestampType(), True)
    ])
    
    data = [
        ("001", "click", datetime(2026, 1, 15, 10, 30), '{"page": "home"}', "web", datetime.now()),
        ("002", "PURCHASE", datetime(2026, 1, 15, 11, 0), '{"amount": 99.99}', "mobile", datetime.now()),
        ("003", "  View  ", datetime(2026, 1, 15, 11, 30), '{"item": "product_a"}', "web", datetime.now()),
        ("001", "click", datetime(2026, 1, 15, 12, 0), '{"page": "checkout"}', "web", datetime.now()),  # Duplicate ID
        (None, "click", datetime(2026, 1, 15, 12, 30), '{}', "web", datetime.now()),  # Null ID
        ("005", None, datetime(2026, 1, 15, 13, 0), '{}', "api", datetime.now()),  # Null event_type
    ]
    
    return spark.createDataFrame(data, schema)


class TestDataQualityRules:
    """Test data quality transformation rules."""
    
    def test_filter_null_ids(self, spark, sample_bronze_data):
        """Test that null IDs are filtered out."""
        result = sample_bronze_data.filter(F.col("id").isNotNull())
        
        assert result.count() == 5
        assert result.filter(F.col("id").isNull()).count() == 0
    
    def test_filter_null_event_types(self, spark, sample_bronze_data):
        """Test that null event_types are filtered out."""
        result = sample_bronze_data.filter(F.col("event_type").isNotNull())
        
        assert result.count() == 5
        assert result.filter(F.col("event_type").isNull()).count() == 0
    
    def test_standardize_event_type(self, spark, sample_bronze_data):
        """Test that event_type is lowercased and trimmed."""
        result = sample_bronze_data \
            .filter(F.col("event_type").isNotNull()) \
            .withColumn("event_type", F.lower(F.trim(F.col("event_type"))))
        
        event_types = [row.event_type for row in result.select("event_type").distinct().collect()]
        
        assert "PURCHASE" not in event_types
        assert "purchase" in event_types
        assert "  View  " not in event_types
        assert "view" in event_types
    
    def test_standardize_source_system(self, spark, sample_bronze_data):
        """Test that source_system is uppercased."""
        result = sample_bronze_data \
            .withColumn("source_system", F.upper(F.trim(F.col("source_system"))))
        
        source_systems = [row.source_system for row in result.select("source_system").distinct().collect()]
        
        assert "WEB" in source_systems
        assert "web" not in source_systems


class TestDeduplication:
    """Test deduplication logic."""
    
    def test_deduplicate_by_id(self, spark, sample_bronze_data):
        """Test that duplicates are removed, keeping latest record."""
        from pyspark.sql.window import Window
        
        window_spec = Window \
            .partitionBy("id") \
            .orderBy(F.col("event_timestamp").desc())
        
        result = sample_bronze_data \
            .filter(F.col("id").isNotNull()) \
            .withColumn("_row_num", F.row_number().over(window_spec)) \
            .filter(F.col("_row_num") == 1) \
            .drop("_row_num")
        
        # Should have 4 unique IDs (001, 002, 003, 005)
        assert result.count() == 4
        
        # For ID 001, should keep the latest (12:00, not 10:30)
        id_001 = result.filter(F.col("id") == "001").collect()[0]
        assert id_001.event_timestamp.hour == 12


class TestPayloadParsing:
    """Test JSON payload parsing."""
    
    def test_parse_json_payload(self, spark, sample_bronze_data):
        """Test that JSON payload is correctly parsed."""
        payload_schema = "page STRING, amount DOUBLE, item STRING"
        
        result = sample_bronze_data \
            .withColumn("payload_parsed", F.from_json(F.col("payload"), payload_schema)) \
            .withColumn("page", F.col("payload_parsed.page")) \
            .withColumn("amount", F.col("payload_parsed.amount")) \
            .withColumn("item", F.col("payload_parsed.item"))
        
        # Check that parsed fields are populated
        home_page = result.filter(F.col("page") == "home").count()
        assert home_page > 0
        
        purchase = result.filter(F.col("amount") == 99.99).count()
        assert purchase == 1
    
    def test_handle_empty_payload(self, spark, sample_bronze_data):
        """Test that empty payloads don't cause errors."""
        payload_schema = "page STRING, amount DOUBLE, item STRING"
        
        result = sample_bronze_data \
            .withColumn("payload_parsed", F.from_json(F.col("payload"), payload_schema))
        
        # Should not raise an exception
        assert result.count() == 6


class TestAggregations:
    """Test gold layer aggregation logic."""
    
    def test_daily_aggregation(self, spark, sample_bronze_data):
        """Test daily event aggregation."""
        result = sample_bronze_data \
            .filter(F.col("id").isNotNull()) \
            .withColumn("event_date", F.to_date("event_timestamp")) \
            .groupBy("event_date") \
            .agg(
                F.count("*").alias("event_count"),
                F.countDistinct("id").alias("unique_ids")
            )
        
        # All events are on same date
        assert result.count() == 1
        
        row = result.collect()[0]
        assert row.event_count == 5  # 5 non-null IDs
        assert row.unique_ids == 4   # 4 unique IDs
    
    def test_event_type_aggregation(self, spark, sample_bronze_data):
        """Test event type aggregation."""
        result = sample_bronze_data \
            .filter(F.col("event_type").isNotNull()) \
            .withColumn("event_type", F.lower(F.trim(F.col("event_type")))) \
            .groupBy("event_type") \
            .agg(F.count("*").alias("count"))
        
        # Should have click, purchase, view
        assert result.count() == 3
        
        click_count = result.filter(F.col("event_type") == "click").collect()[0]["count"]
        assert click_count == 2


class TestMetadataColumns:
    """Test metadata column handling."""
    
    def test_add_processing_timestamp(self, spark, sample_bronze_data):
        """Test that processing timestamp is added correctly."""
        processing_time = datetime.now()
        
        result = sample_bronze_data \
            .withColumn("_processing_timestamp", F.lit(processing_time))
        
        # All rows should have the same processing timestamp
        timestamps = result.select("_processing_timestamp").distinct().collect()
        assert len(timestamps) == 1
    
    def test_add_version_column(self, spark, sample_bronze_data):
        """Test that version column is added correctly."""
        result = sample_bronze_data \
            .withColumn("_version", F.lit(1))
        
        versions = [row._version for row in result.select("_version").distinct().collect()]
        assert versions == [1]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
