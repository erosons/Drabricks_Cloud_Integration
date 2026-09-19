# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 06: Drift Detection for Compliance Dashboard
"""
Step 06: Drift Detection — Compliance Dashboard Integration

Detects drift between the desired state (securables YAML + policies.yml) and
actual Unity Catalog state:
  Stage 1 — Tag drift:   missing / extra schema, table, and COLUMN tags
  Stage 2 — Policy drift: missing / extra ABAC policies on each schema
  Stage 3 — Summary + write to Delta

Writes findings to: general_use.platform_admin.abac_drift_results
and a per-run summary to: general_use.platform_admin.abac_drift_run_summary

ABACConfigLoader is NOT used (deliberately broken in this bundle).
Manifest comes from SDP-META spec tables → UC Volume SecurableRegistry.
"""
import sys
import os
import json
import yaml
import importlib
from datetime import datetime
from pyspark.sql import Row
from pyspark.sql.types import (
    StructType, StructField, StringType, TimestampType,
    IntegerType, BooleanType,
)

dbutils.widgets.text("project_root", "", "Project Root")
dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("bronze_spec_table", "employee_dataflowspec_bronze", "Bronze Spec Table")
dbutils.widgets.text("silver_spec_table", "employee_dataflowspec_silver", "Silver Spec Table")
dbutils.widgets.text("policies_path", "", "Policies Path")
dbutils.widgets.text("mapping_table", "abac_dataflowspec_mapping", "ABAC Mapping Table")
dbutils.widgets.text("exit_on_complete", "false", "Call notebook.exit() at the end")

project_root = dbutils.widgets.get("project_root") or "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac"
catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
bronze_spec_table = dbutils.widgets.get("bronze_spec_table")
silver_spec_table = dbutils.widgets.get("silver_spec_table")
mapping_table = dbutils.widgets.get("mapping_table")
policies_path = dbutils.widgets.get("policies_path") or f"{project_root}/configs/policies.yml"
exit_on_complete = dbutils.widgets.get("exit_on_complete").lower() == "true"

sys.path.insert(0, f"{project_root}/src")
importlib.invalidate_caches()
for _mod in ["config_loader", "spec_table_reader", "policy_inheritance"]:
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])

from spec_table_reader import EnhancedSpecTableABACLoader
from policy_inheritance import apply_inheritance_to_manifest

run_timestamp = datetime.now()

DRIFT_TABLE = f"{catalog}.platform_admin.abac_drift_results"
SUMMARY_TABLE = f"{catalog}.platform_admin.abac_drift_run_summary"

print(f"Drift Detection started at: {run_timestamp.isoformat()}")
print(f"Catalog: {catalog} | Spec schema: {sdp_meta_schema}")
print(f"Drift table:   {DRIFT_TABLE}")
print(f"Summary table: {SUMMARY_TABLE}")

# COMMAND ----------

# DBTITLE 1,Load manifest and build expected state
# Load manifest from spec tables
loader = EnhancedSpecTableABACLoader(
    spark, catalog, sdp_meta_schema,
    bronze_spec_table, silver_spec_table,
    policies_path, mapping_table,
)
manifest = loader.load()
manifest = apply_inheritance_to_manifest(manifest)

# Governed tag keys declared in policies.yml
policy_tag_keys = set(
    t["key"] for t in manifest.policies.get("governed_tags", [])
)

# Expected schema tags: schema_id -> {tag: value}
expected_schema_tags = {}
for sch in manifest.schemas:
    tags = {k: ("" if v is None else str(v))
            for k, v in (sch.get("tags") or {}).items()
            if k in policy_tag_keys}
    if tags:
        expected_schema_tags[sch["schema_id"]] = tags

# Expected table tags: (schema, table) -> {tag: value}
expected_table_tags = {}
for t in manifest.tables:
    tags = {k: ("" if v is None else str(v))
            for k, v in (t.tags or {}).items()
            if k in policy_tag_keys}
    if tags:
        expected_table_tags[(t.schema, t.table_id)] = tags

# Expected column tags: (schema, table) -> set of column names
# Read from raw securables to get mnpi_masked_columns / information_schema flags
volume_base = f"/Volumes/{catalog}/platform_admin/sdp_meta_files/conf/abac"
raw_table_cfgs = {}
for fname in ["bronze_securables.yml", "silver_securables.yml"]:
    try:
        with open(f"{volume_base}/{fname}") as f:
            raw = yaml.safe_load(f)
        for sch in raw.get("schemas", []):
            for tbl in sch.get("tables", []):
                raw_table_cfgs[(sch["schema_id"], tbl["table_id"])] = {
                    "information_schema": tbl.get("information_schema", False),
                    "mnpi_masked_columns": tbl.get("mnpi_masked_columns", []),
                }
    except FileNotFoundError:
        pass

# Expected policy bindings: schema_id -> set of policy_ids
expected_policies = {}
for sch in manifest.schemas:
    pids = set(sch.get("policy_bindings") or [])
    if pids:
        expected_policies[sch["schema_id"]] = pids

print(f"Tables in manifest: {manifest.stats['total_tables']}")
print(f"Expected schema tags: {len(expected_schema_tags)}")
print(f"Expected table tags:  {len(expected_table_tags)}")
print(f"Expected policies:    {sum(len(v) for v in expected_policies.values())} "
      f"across {len(expected_policies)} schemas")
print(f"Governed tag keys:    {sorted(policy_tag_keys)}")

# COMMAND ----------

# DBTITLE 1,Stage 1: Tag drift (schema + table + column)
# ============================================================================
# STAGE 1: TAG DRIFT
# ============================================================================
# Compare expected tags (from securables registry) against actual UC state.
# Three levels: schema tags, table tags, column tags.
# Drift types:
#   MISSING_SCHEMA_TAG  — expected tag absent from UC schema
#   MISSING_TABLE_TAG   — expected tag absent from UC table
#   MISSING_COLUMN_TAG  — expected column tag absent from UC column
#   EXTRA_COLUMN_TAG    — governed column tag in UC not declared in config
# ============================================================================
print("STAGE 1: TAG DRIFT")
print("=" * 78)

all_findings = []

# 1a. Schema-level tags
actual_schema_tags = {}
for r in spark.sql(f"""
    SELECT schema_name, tag_name, tag_value
    FROM system.information_schema.schema_tags
    WHERE catalog_name = '{catalog}'
    ORDER BY schema_name, tag_name
""").collect():
    actual_schema_tags.setdefault(r.schema_name, {})[r.tag_name] = r.tag_value

for sid, expected in expected_schema_tags.items():
    actual = actual_schema_tags.get(sid, {})
    for tag, val in expected.items():
        if tag not in actual:
            all_findings.append({
                "type": "MISSING_SCHEMA_TAG", "severity": "HIGH",
                "fqn": f"{catalog}.{sid}", "column": None,
                "message": f"Schema {sid} missing tag '{tag}'",
            })
            print(f"  HIGH  {catalog}.{sid}: MISSING tag '{tag}'")
        else:
            print(f"  OK    {catalog}.{sid}: tag '{tag}' present")

# 1b. Table-level tags
actual_table_tags = {}
for r in spark.sql(f"""
    SELECT schema_name, table_name, tag_name, tag_value
    FROM {catalog}.information_schema.table_tags
    ORDER BY schema_name, table_name, tag_name
""").collect():
    actual_table_tags.setdefault((r.schema_name, r.table_name), {})[r.tag_name] = r.tag_value

for (schema, table), expected in expected_table_tags.items():
    actual = actual_table_tags.get((schema, table), {})
    fqn = f"{catalog}.{schema}.{table}"
    for tag, val in expected.items():
        if tag not in actual:
            all_findings.append({
                "type": "MISSING_TABLE_TAG", "severity": "HIGH",
                "fqn": fqn, "column": None,
                "message": f"Table {fqn} missing tag '{tag}'",
            })
            print(f"  HIGH  {fqn}: MISSING tag '{tag}'")

# 1c. Column-level tags (mnpi_column_masked)
# Expected: every table with a mnpi_column_masked TABLE tag should have
# STRING columns tagged at column level.  We use the same logic as 02:
# info_schema=true → all STRING, else mnpi_masked_columns filtered to STRING.
actual_col_tags = {}
for r in spark.sql(f"""
    SELECT schema_name, table_name, column_name, tag_name
    FROM {catalog}.information_schema.column_tags
    WHERE tag_name = 'mnpi_column_masked'
    ORDER BY 1, 2, 3
""").collect():
    actual_col_tags.setdefault((r.schema_name, r.table_name), set()).add(r.column_name)

expected_col_tags = {}  # (schema, table) -> set of column names
for t in manifest.tables:
    if "mnpi_column_masked" not in (t.tags or {}):
        continue
    fqn = f"{t.catalog}.{t.schema}.{t.table_id}"
    raw_cfg = raw_table_cfgs.get((t.schema, t.table_id), {})
    use_info = raw_cfg.get("information_schema", False)
    declared = raw_cfg.get("mnpi_masked_columns", []) or []

    try:
        cols = spark.sql(f"""
            SELECT column_name, data_type
            FROM {t.catalog}.information_schema.columns
            WHERE table_schema = '{t.schema}' AND table_name = '{t.table_id}'
        """).collect()
    except Exception:
        continue
    string_cols = {c.column_name for c in cols
                   if str(c.data_type).upper() in ("STRING", "VARCHAR")}
    if use_info:
        exp_cols = string_cols
    elif declared:
        exp_cols = {c for c in declared if c in string_cols}
        if not exp_cols and string_cols:
            exp_cols = string_cols  # fallback
    else:
        exp_cols = string_cols

    expected_col_tags[(t.schema, t.table_id)] = exp_cols
    actual = actual_col_tags.get((t.schema, t.table_id), set())
    missing = exp_cols - actual
    extra = actual - exp_cols
    for c in sorted(missing):
        all_findings.append({
            "type": "MISSING_COLUMN_TAG", "severity": "HIGH",
            "fqn": fqn, "column": c,
            "message": f"{fqn}.{c} missing column tag 'mnpi_column_masked'",
        })
        print(f"  HIGH  {fqn}.{c}: MISSING column tag")
    for c in sorted(extra):
        all_findings.append({
            "type": "EXTRA_COLUMN_TAG", "severity": "MEDIUM",
            "fqn": fqn, "column": c,
            "message": f"{fqn}.{c} has column tag 'mnpi_column_masked' not in config",
        })
        print(f"  MEDIUM {fqn}.{c}: EXTRA column tag")

tag_findings = len(all_findings)
print(f"\n  Tag drift findings: {tag_findings}")
if tag_findings == 0:
    print("  \u2713 All tags match expected state")

# COMMAND ----------

# DBTITLE 1,Stage 2: Policy drift
# ============================================================================
# STAGE 2: POLICY DRIFT
# ============================================================================
# Compare expected ABAC policies (from schema policy_bindings) against actual
# UC policies (SHOW POLICIES ON SCHEMA).
# Drift types:
#   MISSING_POLICY — expected policy not found on the schema
#   EXTRA_POLICY   — policy on schema not declared in config
# ============================================================================
print("\nSTAGE 2: POLICY DRIFT")
print("=" * 78)

for sid, expected_pids in expected_policies.items():
    sfqn = f"{catalog}.{sid}"
    try:
        rows = spark.sql(f"SHOW POLICIES ON SCHEMA {sfqn}").collect()
        actual_pids = {r["Policy Name"] for r in rows}
    except Exception as e:
        all_findings.append({
            "type": "POLICY_CHECK_ERROR", "severity": "HIGH",
            "fqn": sfqn, "column": None,
            "message": f"Cannot check policies on {sfqn}: {str(e)[:120]}",
        })
        print(f"  ERROR {sfqn}: {str(e)[:120]}")
        continue

    missing = expected_pids - actual_pids
    extra = actual_pids - expected_pids

    for pid in sorted(missing):
        all_findings.append({
            "type": "MISSING_POLICY", "severity": "HIGH",
            "fqn": sfqn, "column": None,
            "message": f"Schema {sfqn} missing expected policy '{pid}'",
        })
        print(f"  HIGH  {sfqn}: MISSING policy '{pid}'")

    for pid in sorted(extra):
        all_findings.append({
            "type": "EXTRA_POLICY", "severity": "MEDIUM",
            "fqn": sfqn, "column": None,
            "message": f"Schema {sfqn} has undeclared policy '{pid}'",
        })
        print(f"  MEDIUM {sfqn}: EXTRA policy '{pid}'")

    if not missing and not extra:
        print(f"  OK    {sfqn}: {sorted(actual_pids)}")

policy_findings = len(all_findings) - tag_findings
print(f"\n  Policy drift findings: {policy_findings}")
if policy_findings == 0:
    print("  \u2713 All policies match expected state")

# Categorize
high_severity = [f for f in all_findings if f.get("severity") == "HIGH"]
medium_severity = [f for f in all_findings if f.get("severity") == "MEDIUM"]
low_severity = [f for f in all_findings if f.get("severity") == "LOW"]

print(f"\n{'=' * 78}")
print("DRIFT DETECTION SUMMARY")
print(f"{'=' * 78}")
print(f"  HIGH severity:    {len(high_severity)}")
print(f"  MEDIUM severity:  {len(medium_severity)}")
print(f"  LOW severity:     {len(low_severity)}")
print(f"  Total findings:   {len(all_findings)}")

# COMMAND ----------

# DBTITLE 1,Write results to Delta for compliance dashboard
# Write findings to Delta for the compliance dashboard
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
                                  if k not in ("type", "severity", "fqn",
                                               "message", "column")}),
        is_resolved=False,
    ))

if rows:
    drift_df = spark.createDataFrame(rows, drift_schema)
    drift_df.write.format("delta").mode("append").saveAsTable(DRIFT_TABLE)
    print(f"\n\u2713 Written {len(rows)} drift findings to {DRIFT_TABLE}")
else:
    print(f"\n\u2713 No drift detected — governance state matches config")

# Write per-run summary
summary_schema = StructType([
    StructField("run_timestamp", TimestampType(), False),
    StructField("schemas_checked", IntegerType(), False),
    StructField("tables_checked", IntegerType(), False),
    StructField("column_tag_tables", IntegerType(), False),
    StructField("findings_high", IntegerType(), False),
    StructField("findings_medium", IntegerType(), False),
    StructField("findings_low", IntegerType(), False),
    StructField("findings_total", IntegerType(), False),
])

summary_row = Row(
    run_timestamp=run_timestamp,
    schemas_checked=len(expected_policies),
    tables_checked=len(expected_table_tags),
    column_tag_tables=len(expected_col_tags),
    findings_high=len(high_severity),
    findings_medium=len(medium_severity),
    findings_low=len(low_severity),
    findings_total=len(all_findings),
)

summary_df = spark.createDataFrame([summary_row], summary_schema)
summary_df.write.format("delta").mode("append").option("mergeSchema", "true").saveAsTable(SUMMARY_TABLE)
print(f"\u2713 Written run summary to {SUMMARY_TABLE}")

summary_str = (
    f"findings={len(all_findings)}, high={len(high_severity)}, "
    f"medium={len(medium_severity)}, low={len(low_severity)}"
)
print(f"\nSUMMARY: {summary_str}")

if exit_on_complete:
    dbutils.notebook.exit(summary_str)