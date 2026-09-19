# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,ABAC Governance Orchestrator - Runs All Steps (00-06)
"""
ABAC Governance Orchestrator

This notebook runs all ABAC governance steps in sequence:
  00. Load ABAC Mapping
  01. Load Governance Manifest
  02. Apply Governed Tags
  03. Deploy Masking UDFs
  03b. Grant RBAC Permissions
  04. Create ABAC Policies
  05. Validate Enforcement
  06. Drift Detection

This is designed to be called as a single task after SDP-META pipelines complete.
"""

import logging
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("abac_orchestrator")

# Get parameters
dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("bronze_spec_table", "employee_dataflowspec_bronze", "Bronze Spec Table")
dbutils.widgets.text("silver_spec_table", "employee_dataflowspec_silver", "Silver Spec Table")
dbutils.widgets.text("uc_volume_path", "/Volumes/general_use/platform_admin/sdp_meta_files", "UC Volume Path")
dbutils.widgets.text("project_root", "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac", "Project Root")
dbutils.widgets.text("skip_validation", "false", "Skip Validation Step (true/false)")
dbutils.widgets.text("policies_path", "", "Policies Path (blank = {project_root}/configs/policies.yml)")
dbutils.widgets.text("mapping_table", "abac_dataflowspec_mapping", "ABAC Mapping Table")
dbutils.widgets.text("dry_run", "false", "Dry run — preview only, mutate nothing (propagated to 02/03/04)")
dbutils.widgets.text("grant_rbac_permissions", "true", "Actually execute GRANT statements in 03b")
dbutils.widgets.text("exit_on_complete", "false", "Call notebook.exit() at the end (true for job runs)")

catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
bronze_spec_table = dbutils.widgets.get("bronze_spec_table")
silver_spec_table = dbutils.widgets.get("silver_spec_table")
uc_volume_path = dbutils.widgets.get("uc_volume_path")
project_root = dbutils.widgets.get("project_root")
skip_validation = dbutils.widgets.get("skip_validation").lower() == "true"
policies_path = dbutils.widgets.get("policies_path")
mapping_table = dbutils.widgets.get("mapping_table")
dry_run = dbutils.widgets.get("dry_run").lower() == "true"
grant_rbac_permissions = dbutils.widgets.get("grant_rbac_permissions").lower() == "true"
exit_on_complete = dbutils.widgets.get("exit_on_complete").lower() == "true"

# Arguments every rewired child notebook accepts. Passing the spec-table and
# policies coordinates explicitly means the orchestrator's widgets actually
# propagate instead of each child silently falling back to its own defaults.
#
# use_cached_manifest is pinned to "false" on purpose. With "true" the children
# load a PICKLED manifest from {catalog}.{sdp_meta_schema}.manifest_cache, which
# silently predates any config change and fails with the misleading
# "No 'grants' section found in policies.yml" even when that file is correct.
COMMON_ARGS = {
    "catalog": catalog,
    "sdp_meta_schema": sdp_meta_schema,
    "bronze_spec_table": bronze_spec_table,
    "silver_spec_table": silver_spec_table,
    "project_root": project_root,
    "policies_path": policies_path,
    "mapping_table": mapping_table,
    "use_cached_manifest": "false",
    "exit_on_complete": "true",
}

print(f"{'='*80}")
print(f"ABAC Governance Orchestrator")
print(f"{'='*80}")
print(f"Started at: {datetime.now()}")
print(f"\nConfiguration:")
print(f"  Catalog: {catalog}")
print(f"  SDP Meta Schema: {sdp_meta_schema}")
print(f"  Bronze Spec: {bronze_spec_table}")
print(f"  Silver Spec: {silver_spec_table}")
print(f"  UC Volume: {uc_volume_path}")
print(f"  Project Root: {project_root}")
print(f"  Skip Validation: {skip_validation}")
print(f"  Dry run: {dry_run}")
print(f"  Execute GRANTs (03b): {grant_rbac_permissions}")
print(f"  Policies path: {policies_path or '(child default)'}")
if dry_run:
    print("\n  DRY RUN \u2014 02/03/04 will preview only; nothing will be mutated.")
else:
    print("\n  APPLY MODE \u2014 tags, UDFs, GRANTs and ABAC policies WILL be written.")
print(f"{'='*80}\n")

# Track execution times
step_times = {}
start_time = datetime.now()

# COMMAND ----------

# DBTITLE 1,Step 00: Load ABAC Mapping from Onboarding JSON
print(f"\n{'='*80}")
print(f"Step 1/7: Load ABAC Mapping from Onboarding JSON")
print(f"{'='*80}\n")

step_start = datetime.now()

try:
    result_00 = dbutils.notebook.run(
        f"{project_root}/src/notebooks/00_load_abac_mapping",
        timeout_seconds=600,
        arguments={
            "catalog": catalog,
            "sdp_meta_schema": sdp_meta_schema,
            "uc_volume_path": uc_volume_path,
        }
    )

    step_times["00_load_abac_mapping"] = (datetime.now() - step_start).total_seconds()
    print(f"✓ Step 1 completed in {step_times['00_load_abac_mapping']:.1f}s")
    print(f"  Result: {result_00}")

except Exception as e:
    print(f"✗ Step 1 FAILED: {e}")
    raise

# COMMAND ----------

# DBTITLE 1,Step 01: Load Governance Manifest from Spec Tables
print(f"\n{'='*80}")
print(f"Step 2/7: Load Governance Manifest from Spec Tables")
print(f"{'='*80}\n")

step_start = datetime.now()

try:
    result_01 = dbutils.notebook.run(
        f"{project_root}/src/notebooks/01_load_from_spec_tables",
        timeout_seconds=600,
        arguments={**COMMON_ARGS, "use_mapping_table": "true"}
    )

    step_times["01_load_governance_manifest"] = (datetime.now() - step_start).total_seconds()
    print(f"✓ Step 2 completed in {step_times['01_load_governance_manifest']:.1f}s")
    print(f"  Result: {result_01}")

except Exception as e:
    print(f"✗ Step 2 FAILED: {e}")
    raise

# COMMAND ----------

# DBTITLE 1,Step 02: Apply Governed Tags (Parallel Execution)
print(f"\n{'='*80}")
print(f"Step 3/7: Apply Governed Tags (Parallel Execution)")
print(f"{'='*80}\n")

step_start = datetime.now()

try:
    result_02 = dbutils.notebook.run(
        f"{project_root}/src/notebooks/02_apply_governed_tags",
        timeout_seconds=1800,
        # exit_on_complete MUST stay "false" for 02. Its dbutils.notebook.exit()
        # sits in the table-tag cell, which is NOT the last cell - COLUMN-level
        # tagging runs after it. With exit_on_complete=true the notebook exits
        # early and silently skips every column tag while still reporting
        # success, which leaves ABAC column masks unable to bind. Cost: this
        # step returns None instead of a summary string.
        arguments={
            **COMMON_ARGS,
            "exit_on_complete": "false",
            "dry_run": str(dry_run).lower(),
            "ensure_governed_tags": "true",
        }
    )

    step_times["02_apply_governed_tags"] = (datetime.now() - step_start).total_seconds()
    print(f"✓ Step 3 completed in {step_times['02_apply_governed_tags']:.1f}s")
    print(f"  Result: {result_02}")

except Exception as e:
    print(f"✗ Step 3 FAILED: {e}")
    raise

# COMMAND ----------

# DBTITLE 1,Step 03: Deploy Masking UDFs
print(f"\n{'='*80}")
print(f"Step 4/7: Deploy Masking UDFs")
print(f"{'='*80}\n")

step_start = datetime.now()

try:
    result_03 = dbutils.notebook.run(
        f"{project_root}/src/notebooks/03_deploy_masking_udfs",
        timeout_seconds=600,
        # 03 reads its UDF target from the policies.yml udf_registry
        # (general_use.platform_admin), so no catalog/schema argument is needed.
        arguments={**COMMON_ARGS, "dry_run": str(dry_run).lower()}
    )

    step_times["03_deploy_masking_udfs"] = (datetime.now() - step_start).total_seconds()
    print(f"✓ Step 4 completed in {step_times['03_deploy_masking_udfs']:.1f}s")
    print(f"  Result: {result_03}")

except Exception as e:
    print(f"✗ Step 4 FAILED: {e}")
    raise

# COMMAND ----------

# DBTITLE 1,Step 03b: Grant RBAC Permissions (Parallel Execution)
print(f"\n{'='*80}")
print(f"Step 5/7: Grant RBAC Permissions (Parallel Execution)")
print(f"{'='*80}\n")

step_start = datetime.now()

try:
    result_03b = dbutils.notebook.run(
        f"{project_root}/src/notebooks/03b_grant_rbac_permissions",
        timeout_seconds=1800,
        arguments={
            **COMMON_ARGS,
            "config_path": f"{project_root}/configs",
            # 03b only ever issues GRANT, never REVOKE — it cannot clean up the
            # orphaned ACLs pointing at deleted groups.
            "grant_rbac_permissions": (
                "false" if dry_run else str(grant_rbac_permissions).lower()
            ),
            "fail_on_mismatch": "true",
        }
    )

    step_times["03b_grant_rbac_permissions"] = (datetime.now() - step_start).total_seconds()
    print(f"✓ Step 5 completed in {step_times['03b_grant_rbac_permissions']:.1f}s")
    print(f"  Result: {result_03b}")

except Exception as e:
    print(f"✗ Step 5 FAILED: {e}")
    raise

# COMMAND ----------

# DBTITLE 1,Step 04: Create ABAC Policies (Parallel Execution)
print(f"\n{'='*80}")
print(f"Step 6/7: Create ABAC Policies (Parallel Execution)")
print(f"{'='*80}\n")

step_start = datetime.now()

try:
    result_04 = dbutils.notebook.run(
        f"{project_root}/src/notebooks/04_create_abac_policies",
        timeout_seconds=1800,
        # NOTE: 04's own dry_run widget defaults to "true". It MUST be passed
        # explicitly or the orchestrator creates zero policies while still
        # reporting success.
        arguments={**COMMON_ARGS, "dry_run": str(dry_run).lower()}
    )

    step_times["04_create_abac_policies"] = (datetime.now() - step_start).total_seconds()
    print(f"✓ Step 6 completed in {step_times['04_create_abac_policies']:.1f}s")
    print(f"  Result: {result_04}")

except Exception as e:
    print(f"✗ Step 6 FAILED: {e}")
    raise

# COMMAND ----------

# DBTITLE 1,Step 05: Validate Enforcement (Optional)
if not skip_validation:
    print(f"\n{'='*80}")
    print(f"Step 7/7: Validate Enforcement (Sample-Based)")
    print(f"{'='*80}\n")

    step_start = datetime.now()

    try:
        result_05 = dbutils.notebook.run(
            f"{project_root}/src/notebooks/05_validate_enforcement",
            timeout_seconds=900,
            arguments={**COMMON_ARGS, "sample_size": "10"}
        )

        step_times["05_validate_enforcement"] = (datetime.now() - step_start).total_seconds()
        print(f"✓ Step 7 completed in {step_times['05_validate_enforcement']:.1f}s")
        print(f"  Result: {result_05}")

    except Exception as e:
        print(f"⚠ Step 7 failed (non-critical): {e}")
        # Don't raise - validation is optional
else:
    print(f"\n⚠ Skipping enforcement validation (skip_validation=true)")

# COMMAND ----------

# DBTITLE 1,Step 06: Drift Detection (Compliance Dashboard)
print(f"\n{'='*80}")
print(f"Final Step: Drift Detection (Compliance Dashboard)")
print(f"{'='*80}\n")

step_start = datetime.now()

try:
    result_06 = dbutils.notebook.run(
        f"{project_root}/src/notebooks/06_drift_detection",
        timeout_seconds=600,
        # 06 writes to general_use.platform_admin.abac_drift_results and
        # .abac_drift_run_summary (fixed names, no drift_table argument).
        arguments={**COMMON_ARGS}
    )

    step_times["06_drift_detection"] = (datetime.now() - step_start).total_seconds()
    print(f"✓ Drift detection completed in {step_times['06_drift_detection']:.1f}s")
    print(f"  Result: {result_06}")

except Exception as e:
    print(f"⚠ Drift detection failed (non-critical): {e}")
    # Don't raise - drift detection is logging only

# COMMAND ----------

# DBTITLE 1,Summary Report
total_time = (datetime.now() - start_time).total_seconds()

print(f"\n{'='*80}")
print(f"✓ ABAC GOVERNANCE COMPLETED SUCCESSFULLY")
print(f"{'='*80}\n")
print(f"Total execution time: {total_time:.1f}s ({total_time/60:.1f} minutes)\n")
print(f"Step Execution Times:")
print(f"  00. Load ABAC Mapping:       {step_times.get('00_load_abac_mapping', 0):.1f}s")
print(f"  01. Load Governance:          {step_times.get('01_load_governance_manifest', 0):.1f}s")
print(f"  02. Apply Tags:               {step_times.get('02_apply_governed_tags', 0):.1f}s")
print(f"  03. Deploy UDFs:              {step_times.get('03_deploy_masking_udfs', 0):.1f}s")
print(f"  03b. Grant Permissions:       {step_times.get('03b_grant_rbac_permissions', 0):.1f}s")
print(f"  04. Create Policies:          {step_times.get('04_create_abac_policies', 0):.1f}s")
print(f"  05. Validate:                 {step_times.get('05_validate_enforcement', 0):.1f}s")
print(f"  06. Drift Detection:          {step_times.get('06_drift_detection', 0):.1f}s")
print(f"\n{'='*80}\n")
print(f"Governance applied to catalog: {catalog}")
print(f"Compliance logs: {catalog}.platform_admin.abac_drift_results")
print(f"Run summary:     {catalog}.platform_admin.abac_drift_run_summary")
print(f"Mode:            {'DRY RUN (nothing mutated)' if dry_run else 'APPLY'}")
print(f"\nCompleted at: {datetime.now()}")
print(f"{'='*80}\n")

# dbutils.notebook.exit() REPLACES this cell's entire output with the exit
# string, wiping the per-step timings printed above. Only exit when a caller
# actually consumes the return value.
if exit_on_complete:
    dbutils.notebook.exit(
        f"SUCCESS: ABAC governance completed in {total_time:.1f}s, dry_run={dry_run}"
    )

# COMMAND ----------

