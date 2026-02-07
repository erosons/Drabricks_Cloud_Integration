# Databricks notebook source
# MAGIC %md
# MAGIC # Data Quality Checks
# MAGIC 
# MAGIC This notebook performs data quality validation across all medallion layers.
# MAGIC 
# MAGIC **Purpose:** Validate data integrity, completeness, and consistency  
# MAGIC **Frequency:** Run after each pipeline execution  
# MAGIC **Action on Failure:** Alert and optionally halt downstream processes

# COMMAND ----------

# MAGIC %md
# MAGIC ## Configuration

# COMMAND ----------

dbutils.widgets.text("catalog", "dev_catalog", "Target Catalog")
dbutils.widgets.text("schema", "default", "Target Schema")
dbutils.widgets.text("fail_on_error", "true", "Fail job on DQ errors")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
fail_on_error = dbutils.widgets.get("fail_on_error").lower() == "true"

print(f"Catalog: {catalog}")
print(f"Schema: {schema}")
print(f"Fail on Error: {fail_on_error}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Setup

# COMMAND ----------

from pyspark.sql import functions as F
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional

spark.sql(f"USE CATALOG {catalog}")
spark.sql(f"USE SCHEMA {schema}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Data Quality Framework

# COMMAND ----------

@dataclass
class DQCheckResult:
    """Data quality check result."""
    check_name: str
    table_name: str
    check_type: str
    passed: bool
    expected: str
    actual: str
    details: Optional[str] = None

class DataQualityChecker:
    """Data quality validation framework."""
    
    def __init__(self, catalog: str, schema: str):
        self.catalog = catalog
        self.schema = schema
        self.results: List[DQCheckResult] = []
    
    def check_not_null(self, table: str, columns: List[str]) -> List[DQCheckResult]:
        """Check that specified columns have no null values."""
        results = []
        df = spark.table(table)
        
        for col in columns:
            null_count = df.filter(F.col(col).isNull()).count()
            passed = null_count == 0
            
            result = DQCheckResult(
                check_name=f"not_null_{col}",
                table_name=table,
                check_type="NOT_NULL",
                passed=passed,
                expected="0 nulls",
                actual=f"{null_count} nulls",
                details=f"Column: {col}"
            )
            results.append(result)
            self.results.append(result)
        
        return results
    
    def check_unique(self, table: str, columns: List[str]) -> DQCheckResult:
        """Check that specified columns form a unique key."""
        df = spark.table(table)
        total_count = df.count()
        distinct_count = df.select(*columns).distinct().count()
        
        passed = total_count == distinct_count
        duplicate_count = total_count - distinct_count
        
        result = DQCheckResult(
            check_name=f"unique_{'_'.join(columns)}",
            table_name=table,
            check_type="UNIQUE",
            passed=passed,
            expected="0 duplicates",
            actual=f"{duplicate_count} duplicates",
            details=f"Columns: {columns}"
        )
        self.results.append(result)
        return result
    
    def check_row_count(self, table: str, min_rows: int, max_rows: Optional[int] = None) -> DQCheckResult:
        """Check that table has expected row count range."""
        df = spark.table(table)
        count = df.count()
        
        passed = count >= min_rows
        if max_rows:
            passed = passed and count <= max_rows
        
        expected = f">= {min_rows}" + (f" and <= {max_rows}" if max_rows else "")
        
        result = DQCheckResult(
            check_name="row_count",
            table_name=table,
            check_type="ROW_COUNT",
            passed=passed,
            expected=expected,
            actual=f"{count} rows"
        )
        self.results.append(result)
        return result
    
    def check_freshness(self, table: str, timestamp_col: str, max_hours: int) -> DQCheckResult:
        """Check that data is fresh (within specified hours)."""
        df = spark.table(table)
        max_ts = df.agg(F.max(timestamp_col)).collect()[0][0]
        
        if max_ts is None:
            passed = False
            actual = "No data"
        else:
            from datetime import datetime, timedelta
            age_hours = (datetime.now() - max_ts).total_seconds() / 3600
            passed = age_hours <= max_hours
            actual = f"{age_hours:.1f} hours old"
        
        result = DQCheckResult(
            check_name=f"freshness_{timestamp_col}",
            table_name=table,
            check_type="FRESHNESS",
            passed=passed,
            expected=f"<= {max_hours} hours",
            actual=actual
        )
        self.results.append(result)
        return result
    
    def check_referential_integrity(self, source_table: str, source_col: str, 
                                     target_table: str, target_col: str) -> DQCheckResult:
        """Check referential integrity between tables."""
        source_df = spark.table(source_table).select(source_col).distinct()
        target_df = spark.table(target_table).select(target_col).distinct()
        
        orphans = source_df.join(target_df, source_df[source_col] == target_df[target_col], "left_anti")
        orphan_count = orphans.count()
        
        passed = orphan_count == 0
        
        result = DQCheckResult(
            check_name=f"ref_integrity_{source_table}_{target_table}",
            table_name=source_table,
            check_type="REFERENTIAL_INTEGRITY",
            passed=passed,
            expected="0 orphans",
            actual=f"{orphan_count} orphan records",
            details=f"{source_table}.{source_col} -> {target_table}.{target_col}"
        )
        self.results.append(result)
        return result
    
    def check_value_range(self, table: str, column: str, min_val: float = None, 
                          max_val: float = None) -> DQCheckResult:
        """Check that column values are within expected range."""
        df = spark.table(table)
        stats = df.agg(
            F.min(column).alias("min_val"),
            F.max(column).alias("max_val")
        ).collect()[0]
        
        actual_min = stats["min_val"]
        actual_max = stats["max_val"]
        
        passed = True
        if min_val is not None and actual_min is not None:
            passed = passed and actual_min >= min_val
        if max_val is not None and actual_max is not None:
            passed = passed and actual_max <= max_val
        
        expected = f"[{min_val}, {max_val}]"
        actual = f"[{actual_min}, {actual_max}]"
        
        result = DQCheckResult(
            check_name=f"value_range_{column}",
            table_name=table,
            check_type="VALUE_RANGE",
            passed=passed,
            expected=expected,
            actual=actual,
            details=f"Column: {column}"
        )
        self.results.append(result)
        return result
    
    def get_summary(self) -> dict:
        """Get summary of all check results."""
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = total - passed
        
        return {
            "total_checks": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": f"{(passed/total)*100:.1f}%" if total > 0 else "N/A",
            "failed_checks": [r for r in self.results if not r.passed]
        }

# COMMAND ----------

# MAGIC %md
# MAGIC ## Execute Data Quality Checks

# COMMAND ----------

dq = DataQualityChecker(catalog, schema)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Bronze Layer Checks

# COMMAND ----------

bronze_table = "bronze_events"

# Check table exists and has data
dq.check_row_count(bronze_table, min_rows=1)

# Check required columns are not null
dq.check_not_null(bronze_table, ["id", "_ingestion_timestamp"])

# Check data freshness
dq.check_freshness(bronze_table, "_ingestion_timestamp", max_hours=24)

print("Bronze layer checks complete")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Silver Layer Checks

# COMMAND ----------

silver_table = "silver_events"

# Row count
dq.check_row_count(silver_table, min_rows=1)

# Key columns not null
dq.check_not_null(silver_table, ["id", "event_type"])

# Uniqueness on business key
dq.check_unique(silver_table, ["id"])

# Freshness
dq.check_freshness(silver_table, "_silver_processed_at", max_hours=24)

# Value range for amount (if applicable)
dq.check_value_range(silver_table, "amount", min_val=0, max_val=1000000)

print("Silver layer checks complete")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Gold Layer Checks

# COMMAND ----------

gold_tables = [
    "gold_daily_event_summary",
    "gold_event_type_metrics",
    "gold_rolling_metrics"
]

for table in gold_tables:
    try:
        dq.check_row_count(table, min_rows=1)
        dq.check_freshness(table, "_gold_processed_at", max_hours=24)
    except Exception as e:
        print(f"Warning: Could not check {table}: {e}")

print("Gold layer checks complete")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Results Summary

# COMMAND ----------

summary = dq.get_summary()

print("=" * 60)
print("DATA QUALITY CHECK SUMMARY")
print("=" * 60)
print(f"Total Checks:  {summary['total_checks']}")
print(f"Passed:        {summary['passed']}")
print(f"Failed:        {summary['failed']}")
print(f"Pass Rate:     {summary['pass_rate']}")
print("=" * 60)

# COMMAND ----------

# Display all results
results_data = [
    {
        "check_name": r.check_name,
        "table": r.table_name,
        "type": r.check_type,
        "status": "PASS" if r.passed else "FAIL",
        "expected": r.expected,
        "actual": r.actual,
        "details": r.details or ""
    }
    for r in dq.results
]

results_df = spark.createDataFrame(results_data)
display(results_df)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Handle Failures

# COMMAND ----------

if summary['failed'] > 0:
    print("\n⚠️ FAILED CHECKS:")
    for check in summary['failed_checks']:
        print(f"  - {check.table_name}.{check.check_name}: Expected {check.expected}, got {check.actual}")
    
    if fail_on_error:
        raise Exception(f"Data quality checks failed: {summary['failed']} checks did not pass")
    else:
        print("\n⚠️ Continuing despite failures (fail_on_error=false)")
else:
    print("\n✅ All data quality checks passed!")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Output Results

# COMMAND ----------

dbutils.notebook.exit({
    "status": "SUCCESS" if summary['failed'] == 0 else "FAILED",
    "total_checks": summary['total_checks'],
    "passed": summary['passed'],
    "failed": summary['failed'],
    "pass_rate": summary['pass_rate']
})
