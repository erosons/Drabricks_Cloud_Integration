# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 02: Apply Governed Tags (Parallel)
"""
Step 02: Apply Governed Tags — Parallelized for 2000+ tables

1. Load manifest (multi-file config + templates)
2. For each table, resolve template column_patterns against actual columns
3. Apply governed tags using ALTER TABLE ... SET TAGS in parallel batches
4. Log results for audit trail
"""
import sys
import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("abac_mvp2.apply_tags")

dbutils.widgets.text("config_path", "", "Config Directory")
dbutils.widgets.text("project_root", "", "Project Root")

config_path = dbutils.widgets.get("config_path") or "/Workspace/abac-mvp2/configs" or "/Workspace/abac-mvp2/configs"
project_root = dbutils.widgets.get("project_root") or "/Workspace/abac-mvp2"

sys.path.insert(0, f"{project_root}/src")
from config_loader import (
    ABACConfigLoader, TemplateResolver,
    ParallelGovernanceExecutor, ResolvedTable
)

print(f"Loading governance manifest from: {config_path}")

# COMMAND ----------

# DBTITLE 1,Load manifest and validate tags
# Load manifest
loader = ABACConfigLoader(config_path)
manifest = loader.load()

# Extract governed tag keys from policies
policy_tag_keys = set()
for tag_def in manifest.policies.get("governed_tags", []):
    policy_tag_keys.add(tag_def["key"])

print(f"Governed tags declared in policies: {len(policy_tag_keys)}")
for key in sorted(policy_tag_keys):
    print(f"  - {key}")

print(f"\nTables to process: {manifest.stats['total_tables']}")

# Initialize template resolver
resolver = TemplateResolver(manifest.templates)

# COMMAND ----------

# DBTITLE 1,Define tag application operation
def apply_tags_to_table(spark_session, table: ResolvedTable):
    """
    Apply governed tags to a single table's columns.
    Uses template pattern matching against actual columns from information_schema.
    """
    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    
    # 1. Get actual columns from information_schema
    try:
        cols_df = spark_session.sql(f"""
            SELECT column_name, data_type
            FROM {table.catalog}.information_schema.columns
            WHERE table_schema = '{table.schema}'
              AND table_name = '{table.table_id}'
            ORDER BY ordinal_position
        """)
        actual_columns = [
            {"name": row.column_name, "type": row.data_type}
            for row in cols_df.collect()
        ]
    except Exception as e:
        return {"status": "failed", "error": f"Cannot read columns: {e}"}

    if not actual_columns:
        return {"status": "skipped", "reason": "table not found or no columns"}

    # 2. Resolve tags using template patterns + overrides
    resolved_columns = resolver.resolve_column_tags(
        table.template or "",
        actual_columns,
        table.column_overrides,
    )

    # 3. Apply tags via ALTER TABLE
    tags_applied = 0
    tags_skipped = 0
    for col in resolved_columns:
        col_tags = col.get("tags", {})
        if not col_tags:
            continue

        # Only apply tags that are declared in policies.yaml
        valid_tags = {
            k: v for k, v in col_tags.items()
            if k in policy_tag_keys
        }
        if not valid_tags:
            tags_skipped += len(col_tags)
            continue

        # Build ALTER TABLE SET TAGS statement
        tag_pairs = ", ".join(
            f"'{k}' = '{v}'" for k, v in valid_tags.items()
        )
        sql = f"ALTER TABLE {fqn} ALTER COLUMN `{col['name']}` SET TAGS ({tag_pairs})"
        
        try:
            spark_session.sql(sql)
            tags_applied += len(valid_tags)
        except Exception as e:
            logger.warning(f"  Tag apply failed for {fqn}.{col['name']}: {e}")

    return {
        "status": "success",
        "tags_applied": tags_applied,
        "tags_skipped": tags_skipped,
        "columns_processed": len(resolved_columns),
    }

# COMMAND ----------

# DBTITLE 1,Execute tag application in parallel batches
# Execute in parallel using the governance executor
executor = ParallelGovernanceExecutor(spark, manifest)
results = executor.execute_in_batches(
    manifest.tables,
    apply_tags_to_table,
    operation_name="apply_governed_tags",
)

print("\n" + "=" * 60)
print("TAG APPLICATION RESULTS")
print("=" * 60)
print(f"  Total tables:  {results['total']}")
print(f"  Success:       {results['success']}")
print(f"  Failed:        {results['failed']}")
print(f"  Skipped:       {results['skipped']}")

# Aggregate tag counts
total_tags = sum(
    d.get("tags_applied", 0)
    for d in results["details"] if d.get("status") == "success"
)
print(f"  Tags applied:  {total_tags}")

if results['failed'] > 0:
    print("\nFailed tables:")
    for d in results["details"]:
        if d.get("status") in ("failed", "error"):
            print(f"  - {d['fqn']}: {d.get('error', 'unknown')}")

dbutils.notebook.exit(f"success={results['success']}, failed={results['failed']}, tags={total_tags}")

# COMMAND ----------

