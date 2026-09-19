# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 01: Load ABAC Config from SDP-META Spec Tables
"""
Step 01: Load ABAC Configuration from SDP-META Dataflowspec Tables

This notebook bridges SDP-META dataflowspec tables to the ABAC governance framework:
  1. Reads bronze/silver dataflowspec tables
  2. Joins with abac_dataflowspec_mapping to get governance paths
  3. Loads governance YAML files from UC Volume
  4. Produces unified GovernanceManifest for ABAC notebooks 02-06

This runs AFTER SDP-META onboarding completes and should be scheduled
to run hourly to keep ABAC governance in sync with pipeline changes.
"""

import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("abac_mvp2.load_spec")

# Widgets
dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("bronze_spec_table", "employee_dataflowspec_bronze", "Bronze Spec Table")
dbutils.widgets.text("silver_spec_table", "employee_dataflowspec_silver", "Silver Spec Table")
dbutils.widgets.text("project_root", "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac", "Project Root")
dbutils.widgets.text("policies_path", "", "Policies Path (defaults to {project_root}/configs/policies.yml)")
dbutils.widgets.text("use_mapping_table", "true", "Use ABAC Mapping Table (true/false)")
dbutils.widgets.text("mapping_table", "abac_dataflowspec_mapping", "ABAC Mapping Table Name")

catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
bronze_spec_table = dbutils.widgets.get("bronze_spec_table")
silver_spec_table = dbutils.widgets.get("silver_spec_table")
project_root = dbutils.widgets.get("project_root")
policies_path = dbutils.widgets.get("policies_path") or f"{project_root}/configs/policies.yml"
use_mapping_table = dbutils.widgets.get("use_mapping_table").lower() == "true"
mapping_table = dbutils.widgets.get("mapping_table")

sys.path.insert(0, f"{project_root}/src")

print(f"Loading ABAC governance from SDP-META spec tables:")
print(f"  Catalog: {catalog}")
print(f"  Schema: {sdp_meta_schema}")
print(f"  Bronze table: {bronze_spec_table}")
print(f"  Silver table: {silver_spec_table}")
print(f"  Policies: {policies_path}")
print(f"  Use mapping table: {use_mapping_table}")
print(f"  Mapping table: {mapping_table}")

# COMMAND ----------

# DBTITLE 1,Load Governance Manifest from Spec Tables
import importlib
import sys

# The modules under {project_root}/src were edited on disk after they were first
# imported into this Python session; the cached (stale) copies are what caused
# 0 tables to load. Reload in dependency order (config_loader first) so
# ResolvedTable/GovernanceManifest come from the current source.
importlib.invalidate_caches()
for _mod in ["config_loader", "spec_table_reader", "policy_inheritance", "mnpi_expiration"]:
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])

from spec_table_reader import SpecTableABACLoader, EnhancedSpecTableABACLoader

if use_mapping_table:
    # Use enhanced loader with ABAC mapping table
    loader = EnhancedSpecTableABACLoader(
        spark=spark,
        catalog=catalog,
        sdp_meta_schema=sdp_meta_schema,
        bronze_spec_table=bronze_spec_table,
        silver_spec_table=silver_spec_table,
        policies_path=policies_path,
        abac_mapping_table=mapping_table
    )
    print(f"\n✓ Using EnhancedSpecTableABACLoader with mapping table: {mapping_table}")
else:
    # Use basic loader (convention-based paths)
    loader = SpecTableABACLoader(
        spark=spark,
        catalog=catalog,
        sdp_meta_schema=sdp_meta_schema,
        bronze_spec_table=bronze_spec_table,
        silver_spec_table=silver_spec_table,
        policies_path=policies_path,
    )
    print("\n✓ Using SpecTableABACLoader (convention-based)")

manifest = loader.load()

print(f"\n✓ Loaded ABAC Governance Manifest:")
print(f"  Bronze flows: {manifest.stats.get('bronze_flows', 0)}")
print(f"  Silver flows: {manifest.stats.get('silver_flows', 0)}")
print(f"  Total tables: {manifest.stats.get('total_tables', 0)}")
print(f"  Policies: {len(manifest.policies.get('policies', {}).get('row_filters', []))} row filters, {len(manifest.policies.get('policies', {}).get('column_masks', []))} masks")

# COMMAND ----------

# DBTITLE 1,Apply Policy Inheritance
from policy_inheritance import apply_inheritance_to_manifest
manifest = apply_inheritance_to_manifest(manifest)

print(f"\n✓ Policy inheritance resolved:")
print(f"  TWO-TIER SCOPING MODEL:")
inheritance_stats = manifest.stats.get("inheritance", {})
print(f"    Schemas with policies (ON SCHEMA): {inheritance_stats.get('schemas_with_policies', 0)}")
print(f"    Schemas delegating to tables (empty policy_bindings): {inheritance_stats.get('schemas_delegating_to_tables', 0)}")
print(f"    Tables with inherited policies: {inheritance_stats.get('tables_with_inherited_policies', 0)}")
print(f"    Tables with direct policies (ON TABLE): {inheritance_stats.get('tables_with_direct_policies', 0)}")

# COMMAND ----------

# DBTITLE 1,Apply MNPI Expiration Dates
from mnpi_expiration import apply_expiration_dates_to_manifest
manifest, expiration_stats = apply_expiration_dates_to_manifest(manifest)

print(f"\n✓ MNPI expiration dates applied:")
print(f"    Explicit expiration: {expiration_stats.get('tables_with_expiration', 0)}")
print(f"    Never expires: {expiration_stats.get('tables_never_expire', 0)}")
print(f"    Auto-assigned (5 days): {expiration_stats.get('tables_auto_assigned', 0)}")

# COMMAND ----------

# DBTITLE 1,Display Loaded Tables
import pandas as pd

# Convert to DataFrame for display
tables_data = []
for table in manifest.tables:
    tables_data.append({
        "table_id": table.table_id,
        "catalog": table.catalog,
        "schema": table.schema,
        "policy_bindings": ", ".join(table.policy_bindings),
        "num_columns": len(table.columns),
        "num_grants": len(table.grants),
        "source_file": table.source_file,
    })

if tables_data:
    tables_df = pd.DataFrame(tables_data)
    print(f"\n{len(tables_data)} tables loaded:")
    display(tables_df)
else:
    print("\n⚠ No tables found with ABAC governance")

# COMMAND ----------

# DBTITLE 1,Cache Manifest for Downstream Notebooks
# Store manifest in dbutils.jobs.taskValues for downstream notebooks
# Or write to a temporary Delta table for complex workflows

import pickle
import base64

# Serialize manifest
manifest_bytes = pickle.dumps(manifest)
manifest_b64 = base64.b64encode(manifest_bytes).decode('utf-8')

# Store in task values (if running in a job)
try:
    dbutils.jobs.taskValues.set(key="manifest", value=manifest_b64)
    print("\n✓ Manifest cached in job task values")
except Exception as e:
    print(f"\n⚠ Could not cache in task values (not running in job): {e}")

# Alternative: Write to temp table
temp_table = f"{catalog}.{sdp_meta_schema}.manifest_cache"
manifest_df = spark.createDataFrame([{"manifest_json": manifest_b64, "loaded_at": spark.sql("SELECT current_timestamp()").collect()[0][0]}])
manifest_df.write.format("delta").mode("overwrite").saveAsTable(temp_table)
print(f"✓ Manifest cached in table: {temp_table}")

print("\n✓ Ready for ABAC notebooks 02-06")