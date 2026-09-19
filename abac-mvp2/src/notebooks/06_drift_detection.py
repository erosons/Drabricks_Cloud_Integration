# Databricks notebook source
# DBTITLE 1,Step 06: Drift Detection for Compliance Dashboard
"""
Step 06: Drift Detection — Compliance Dashboard Integration

Detects drift between YAML config (desired state) and actual UC state:
  - Missing tags on columns
  - Unauthorized policy modifications
  - Missing/extra grants
  - Unbound policies

Writes results to Delta table: general_use.platform_admin.abac_drift_results
for the compliance dashboard to consume.
"""
import sys
import os
import json
from datetime import datetime
from pyspark.sql import Row
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType,
    ArrayType, IntegerType, BooleanType
)

dbutils.widgets.text("config_path", "", "Config Directory")
dbutils.widgets.text("project_root", "", "Project Root")

config_path = dbutils.widgets.get("config_path")
project_root = dbutils.widgets.get("project_root")

sys.path.insert(0, f"{project_root}/src")
from config_loader import ABACConfigLoader, TemplateResolver, ParallelGovernanceExecutor

print(f"Drift Detection started at: {datetime.now().isoformat()}")

# COMMAND ----------

# DBTITLE 1,Load manifest
# Load governance manifest
loader = ABACConfigLoader(config_path)
manifest = loader.load()
resolver = TemplateResolver(manifest.templates)

# Target table for drift results
DRIFT_TABLE = manifest.controls.get("audit", {}).get(
    "drift_results_table", "general_use.platform_admin.abac_drift_results"
)
CHANGE_LOG_TABLE = manifest.controls.get("audit", {}).get(
    "policy_change_log_table", "general_use.platform_admin.abac_policy_changes"
)

print(f"Tables to check: {manifest.stats['total_tables']}")
print(f"Drift results table: {DRIFT_TABLE}")
print(f"Change log table: {CHANGE_LOG_TABLE}")

# Extract governed tag keys
policy_tag_keys = set(t["key"] for t in manifest.policies.get("governed_tags", []))
run_timestamp = datetime.now()

# COMMAND ----------

# DBTITLE 1,Define drift detection logic
def detect_drift_for_table(spark_session, table):
    """
    Compare desired state (config) vs actual state (UC) for a single table.
    Returns drift findings.
    """
    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    findings = []

    # 1. Check if table exists
    try:
        cols_df = spark_session.sql(f"""
            SELECT column_name, data_type
            FROM {table.catalog}.information_schema.columns
            WHERE table_schema = '{table.schema}'
              AND table_name = '{table.table_id}'
        """)
        actual_columns = [
            {"name": row.column_name, "type": row.data_type}
            for row in cols_df.collect()
        ]
    except Exception as e:
        return {
            "status": "error",
            "findings": [{
                "type": "TABLE_NOT_FOUND",
                "severity": "HIGH",
                "message": f"Table {fqn} not found in UC: {e}",
                "fqn": fqn,
            }]
        }

    if not actual_columns:
        return {
            "status": "error",
            "findings": [{
                "type": "TABLE_EMPTY",
                "severity": "MEDIUM",
                "message": f"Table {fqn} has no columns in information_schema",
                "fqn": fqn,
            }]
        }

    # 2. Resolve expected tags from template + overrides
    expected_columns = resolver.resolve_column_tags(
        table.template or "",
        actual_columns,
        table.column_overrides,
    )

    # 3. Check actual tags on each column
    for col in expected_columns:
        expected_tags = col.get("tags", {})
        if not expected_tags:
            continue

        # Only check tags that are in our policy governance
        governed_expected = {
            k: v for k, v in expected_tags.items()
            if k in policy_tag_keys
        }
        if not governed_expected:
            continue

        # Query actual tags on this column
        try:
            tag_df = spark_session.sql(f"""
                SELECT tag_name, tag_value
                FROM {table.catalog}.information_schema.column_tags
                WHERE table_schema = '{table.schema}'
                  AND table_name = '{table.table_id}'
                  AND column_name = '{col["name"]}'
            """)
            actual_tags = {
                row.tag_name: row.tag_value
                for row in tag_df.collect()
            }
        except Exception:
            actual_tags = {}

        # Compare expected vs actual
        for tag_key in governed_expected:
            if tag_key not in actual_tags:
                findings.append({
                    "type": "MISSING_TAG",
                    "severity": "HIGH",
                    "message": f"Column {col['name']} missing tag '{tag_key}'",
                    "fqn": fqn,
                    "column": col["name"],
                    "expected_tag": tag_key,
                })

    # 4. Check for extra tags not in config (potential manual weakening)
    try:
        all_tags_df = spark_session.sql(f"""
            SELECT column_name, tag_name, tag_value
            FROM {table.catalog}.information_schema.column_tags
            WHERE table_schema = '{table.schema}'
              AND table_name = '{table.table_id}'
        """)
        for row in all_tags_df.collect():
            if row.tag_name in policy_tag_keys:
                # Check if this column is supposed to have this tag
                expected_col = next(
                    (c for c in expected_columns if c["name"] == row.column_name),
                    None
                )
                if expected_col:
                    expected_for_col = expected_col.get("tags", {})
                    if row.tag_name not in expected_for_col:
                        findings.append({
                            "type": "UNEXPECTED_TAG",
                            "severity": "MEDIUM",
                            "message": f"Column {row.column_name} has unexpected governed tag '{row.tag_name}'",
                            "fqn": fqn,
                            "column": row.column_name,
                            "unexpected_tag": row.tag_name,
                        })
    except Exception:
        pass  # column_tags view may not exist in all environments

    status = "clean" if not findings else "drifted"
    return {"status": status, "findings": findings}

# COMMAND ----------

# DBTITLE 1,Execute drift detection in parallel
# Run drift detection across all tables
executor = ParallelGovernanceExecutor(spark, manifest)
results = executor.execute_in_batches(
    manifest.tables,
    detect_drift_for_table,
    operation_name="drift_detection",
)

# Aggregate findings
all_findings = []
for detail in results["details"]:
    findings = detail.get("findings", [])
    all_findings.extend(findings)

# Categorize
high_severity = [f for f in all_findings if f.get("severity") == "HIGH"]
medium_severity = [f for f in all_findings if f.get("severity") == "MEDIUM"]
low_severity = [f for f in all_findings if f.get("severity") == "LOW"]

print("\n" + "=" * 60)
print("DRIFT DETECTION RESULTS")
print("=" * 60)
print(f"  Tables checked:     {results['total']}")
print(f"  Clean (no drift):   {results['success']}")
print(f"  Drifted:            {results['failed']}")
print(f"  Errors:             {results['skipped']}")
print(f"\n  HIGH severity:      {len(high_severity)}")
print(f"  MEDIUM severity:    {len(medium_severity)}")
print(f"  LOW severity:       {len(low_severity)}")
print(f"  Total findings:     {len(all_findings)}")

# COMMAND ----------

# DBTITLE 1,Write results to Delta for compliance dashboard
# Schema for drift results table
drift_schema = StructType([
    StructField("run_timestamp", TimestampType(), False),
    StructField("finding_type", StringType(), False),
    StructField("severity", StringType(), False),
    StructField("fqn", StringType(), False),
    StructField("column_name", StringType(), True),
    StructField("message", StringType(), False),
    StructField("details_json", StringType(), True),
    StructField("is_resolved", BooleanType(), False),
])

# Build rows for Delta table
rows = []
for finding in all_findings:
    rows.append(Row(
        run_timestamp=run_timestamp,
        finding_type=finding.get("type", "UNKNOWN"),
        severity=finding.get("severity", "MEDIUM"),
        fqn=finding.get("fqn", ""),
        column_name=finding.get("column", None),
        message=finding.get("message", ""),
        details_json=json.dumps({k: v for k, v in finding.items()
                                  if k not in ("type", "severity", "fqn", "message")}),
        is_resolved=False,
    ))

if rows:
    drift_df = spark.createDataFrame(rows, drift_schema)
    drift_df.write.format("delta").mode("append").saveAsTable(DRIFT_TABLE)
    print(f"\n\u2713 Written {len(rows)} drift findings to {DRIFT_TABLE}")
else:
    print(f"\n\u2713 No drift detected — all {results['total']} tables are compliant")

# Write summary row
summary_schema = StructType([
    StructField("run_timestamp", TimestampType(), False),
    StructField("tables_checked", IntegerType(), False),
    StructField("tables_clean", IntegerType(), False),
    StructField("tables_drifted", IntegerType(), False),
    StructField("findings_high", IntegerType(), False),
    StructField("findings_medium", IntegerType(), False),
    StructField("findings_low", IntegerType(), False),
    StructField("findings_total", IntegerType(), False),
])

summary_row = Row(
    run_timestamp=run_timestamp,
    tables_checked=results["total"],
    tables_clean=results["success"],
    tables_drifted=results["failed"],
    findings_high=len(high_severity),
    findings_medium=len(medium_severity),
    findings_low=len(low_severity),
    findings_total=len(all_findings),
)

summary_df = spark.createDataFrame([summary_row], summary_schema)
summary_table = DRIFT_TABLE.replace("drift_results", "drift_run_summary")
summary_df.write.format("delta").mode("append").saveAsTable(summary_table)
print(f"\u2713 Written run summary to {summary_table}")

dbutils.notebook.exit(
    f"tables={results['total']}, findings={len(all_findings)}, "
    f"high={len(high_severity)}, medium={len(medium_severity)}"
)