#!/usr/bin/env python3
"""Stage conf/ to UC Volume, replace template tokens, and onboard ABAC spec

Copies all files from workspace conf/ directory to UC Volume and replaces
template tokens in text files:
  - {uc_catalog_name} -> actual catalog name
  - {bronze_schema} -> actual bronze schema name
  - {silver_schema} -> actual silver schema name
  - {uc_volume_path} -> actual UC Volume path

If sdp_meta_schema and abac_dataflowspec_table are both given, also loads
conf/abac/securables.yaml (or securables.json) from the just-staged tree
into a Delta "spec table" -- one row per table, capturing catalog, schema,
table_id, policy_bindings, grants, columns, and masking_expiry_date -- so
the ABAC governance framework can read a table's worth of governance
config instead of the raw file. Mirrors the bronze/silver dataflowspec
tables the onboarding wheel task creates for SDP-META pipelines.

Usage:
  stage_conf_with_tokens.py <source_dir> <target_dir> <catalog> <bronze_schema> <silver_schema> <volume_path> [sdp_meta_schema] [abac_dataflowspec_table]
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime, timezone

def replace_tokens(content, catalog, bronze_schema, silver_schema, volume_path):
    """Replace all template tokens in the content"""
    content = content.replace("{uc_catalog_name}", catalog)
    content = content.replace("{bronze_schema}", bronze_schema)
    content = content.replace("{silver_schema}", silver_schema)
    content = content.replace("{uc_volume_path}", volume_path)
    return content

def is_text_file(filename):
    """Check if file should be treated as text"""
    text_extensions = ('.json', '.yaml', '.yml', '.ddl', '.sql', '.txt', '.csv', '.md')
    return filename.lower().endswith(text_extensions)

def stage_conf_tree(source_dir, target_dir, catalog, bronze_schema, silver_schema, volume_path):
    """Copy and process all files from source to target"""
    source_path = Path(source_dir)
    target_path = Path(target_dir)

    if not source_path.exists():
        raise FileNotFoundError(f"Source directory not found: {source_dir}")

    # Create target directory
    target_path.mkdir(parents=True, exist_ok=True)

    staged_count = 0

    # Walk through all files
    for source_file in source_path.rglob('*'):
        if source_file.is_file():
            # Calculate relative path and target location
            rel_path = source_file.relative_to(source_path)
            target_file = target_path / rel_path

            # Create parent directory if needed
            target_file.parent.mkdir(parents=True, exist_ok=True)

            # Process file
            if is_text_file(source_file.name):
                # Read, replace tokens, write
                content = source_file.read_text(encoding='utf-8')
                processed = replace_tokens(content, catalog, bronze_schema, silver_schema, volume_path)
                target_file.write_text(processed, encoding='utf-8')
                print(f"Staged (with tokens): {source_file} -> {target_file}")
            else:
                # Binary copy
                target_file.write_bytes(source_file.read_bytes())
                print(f"Staged (binary): {source_file} -> {target_file}")

            staged_count += 1

    return staged_count


def _load_abac_config(path):
    """Load securables.yaml or securables.json (whichever extension)."""
    import yaml
    with open(path, "r") as f:
        if path.lower().endswith(".json"):
            return json.load(f) or {}
        return yaml.safe_load(f) or {}


def load_abac_securables_to_table(staged_target_dir, catalog, sdp_meta_schema, abac_dataflowspec_table):
    """Load the staged conf/abac/securables.yaml (or .json) into a Delta
    spec table: <catalog>.<sdp_meta_schema>.<abac_dataflowspec_table>."""
    yaml_path = os.path.join(staged_target_dir, "abac", "securables.yaml")
    json_path = os.path.join(staged_target_dir, "abac", "securables.json")
    source_path = yaml_path if os.path.exists(yaml_path) else json_path
    if not os.path.exists(source_path):
        print(f"No abac/securables.yaml or .json found under {staged_target_dir} -- skipping ABAC spec load")
        return 0

    config = _load_abac_config(source_path)
    loaded_at = datetime.now(timezone.utc)
    rows = []
    for table in config.get("tables", []):
        rows.append({
            "catalog": table.get("catalog", ""),
            "schema": table.get("schema", ""),
            "table_id": table.get("table_id", ""),
            "description": table.get("description", ""),
            "policy_bindings": table.get("policy_bindings", []) or [],
            "grants_json": json.dumps(table.get("grants", {}) or {}),
            "columns_json": json.dumps(table.get("columns", []) or []),
            "masking_expiry_date_json": (
                json.dumps(table["masking_expiry_date"])
                if table.get("masking_expiry_date") else None
            ),
            "source_file": source_path,
            "loaded_at": loaded_at,
        })

    from pyspark.sql import SparkSession
    from pyspark.sql.types import (
        StructType, StructField, StringType, TimestampType, ArrayType,
    )

    spark = SparkSession.builder.getOrCreate()
    schema_struct = StructType([
        StructField("catalog", StringType(), True),
        StructField("schema", StringType(), True),
        StructField("table_id", StringType(), True),
        StructField("description", StringType(), True),
        StructField("policy_bindings", ArrayType(StringType()), True),
        StructField("grants_json", StringType(), True),
        StructField("columns_json", StringType(), True),
        StructField("masking_expiry_date_json", StringType(), True),
        StructField("source_file", StringType(), True),
        StructField("loaded_at", TimestampType(), True),
    ])

    target_table = f"{catalog}.{sdp_meta_schema}.{abac_dataflowspec_table}"
    df = spark.createDataFrame(rows, schema_struct) if rows else spark.createDataFrame([], schema_struct)
    (df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(target_table))
    print(f"Loaded {len(rows)} ABAC table spec(s) from {source_path} into {target_table}")
    return len(rows)


def main():
    if len(sys.argv) < 7:
        print(__doc__)
        sys.exit(1)

    source_dir = sys.argv[1]
    target_dir = sys.argv[2]
    catalog = sys.argv[3]
    bronze_schema = sys.argv[4]
    silver_schema = sys.argv[5]
    volume_path = sys.argv[6]
    sdp_meta_schema = sys.argv[7] if len(sys.argv) > 7 else None
    abac_dataflowspec_table = sys.argv[8] if len(sys.argv) > 8 else None

    print(f"Staging conf files with token replacement:")
    print(f"  Source: {source_dir}")
    print(f"  Target: {target_dir}")
    print(f"  Tokens:")
    print(f"    {{uc_catalog_name}} -> {catalog}")
    print(f"    {{bronze_schema}} -> {bronze_schema}")
    print(f"    {{silver_schema}} -> {silver_schema}")
    print(f"    {{uc_volume_path}} -> {volume_path}")
    print()

    count = stage_conf_tree(source_dir, target_dir, catalog, bronze_schema, silver_schema, volume_path)

    print(f"\nStaged {count} file(s) to {target_dir}")

    if sdp_meta_schema and abac_dataflowspec_table:
        print()
        load_abac_securables_to_table(target_dir, catalog, sdp_meta_schema, abac_dataflowspec_table)

if __name__ == "__main__":
    main()
