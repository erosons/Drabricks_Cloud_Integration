# Databricks notebook source
# DBTITLE 1,ABAC MVP2 — Scalable Governance Deployment
# MAGIC %md
# MAGIC # ABAC MVP2 — Scalable Governance Framework
# MAGIC
# MAGIC Orchestrates governance deployment for **2000+ tables** using:
# MAGIC - Multi-file config with template resolution
# MAGIC - Parallel execution (ThreadPoolExecutor)
# MAGIC - Auto-discovery from `information_schema`
# MAGIC
# MAGIC | Step | Notebook | Purpose |
# MAGIC |------|----------|---------|
# MAGIC | 01b | auto_discover_tables | Discover unmanaged tables, generate config stubs |
# MAGIC | 02 | apply_governed_tags | Apply tags using template pattern matching |
# MAGIC | 03 | deploy_masking_udfs | Deploy mask/filter UDFs to platform_admin schema |
# MAGIC | 03b | grant_rbac_permissions | Grant base RBAC access per config |
# MAGIC | 04 | create_abac_policies | CREATE POLICY with MATCH COLUMNS for all bindings |
# MAGIC | 05 | validate_enforcement | Verify masking works at runtime (sample) |
# MAGIC | 06 | drift_detection | Detect drift, write results for compliance dashboard |

# COMMAND ----------

# DBTITLE 1,Configuration
import sys
import time

# Add src to path for imports
PROJECT_ROOT = "/Workspace/Users/samson.eromonsei@databricks.com/abac-mvp2"
sys.path.insert(0, f"{PROJECT_ROOT}/src")

from config_loader import ABACConfigLoader, TemplateResolver, ParallelGovernanceExecutor

# Configuration
CONFIG_PATH = f"{PROJECT_ROOT}/configs"
NOTEBOOK_DIR = f"{PROJECT_ROOT}/src/notebooks"
TIMEOUT = 900  # 15 minutes per notebook (scaled for 2000 tables)

print(f"Project root: {PROJECT_ROOT}")
print(f"Config path:  {CONFIG_PATH}")

# COMMAND ----------

# DBTITLE 1,Load & Validate Configuration
# Load the full governance manifest
loader = ABACConfigLoader(CONFIG_PATH)
manifest = loader.load()

print("\n" + "=" * 60)
print("GOVERNANCE MANIFEST LOADED")
print("=" * 60)
print(f"  Catalogs:   {manifest.stats['total_catalogs']}")
print(f"  Schemas:    {manifest.stats['total_schemas']}")
print(f"  Tables:     {manifest.stats['total_tables']}")
print(f"  Templates:  {manifest.stats['total_templates']}")
print(f"  Policies:   {manifest.stats['total_policies']}")
print(f"\n  Parallelism: {manifest.controls.get('reconciliation', {}).get('max_parallel_workers', 10)} workers")
print(f"  Batch size:  {manifest.controls.get('reconciliation', {}).get('batch_size', 50)} tables/batch")

# COMMAND ----------

# DBTITLE 1,Execute Deployment Pipeline
steps = [
    ("01b_auto_discover_tables", "Auto-discover unmanaged tables"),
    ("02_apply_governed_tags", "Apply governed tags (parallel)"),
    ("03_deploy_masking_udfs", "Deploy masking UDFs"),
    ("03b_grant_rbac_permissions", "Grant RBAC permissions (parallel)"),
    ("04_create_abac_policies", "Create ABAC policies"),
    ("05_validate_enforcement", "Validate enforcement (sample)"),
    ("06_drift_detection", "Run drift detection"),
]

results = []
print("\nABAC MVP2 Governance Deployment")
print("=" * 60)

for notebook_name, description in steps:
    path = f"{NOTEBOOK_DIR}/{notebook_name}"
    print(f"\n\u25b6 Step: {description}")
    print(f"  Notebook: {path}")

    start = time.time()
    try:
        result = dbutils.notebook.run(path, TIMEOUT, {
            "config_path": CONFIG_PATH,
            "project_root": PROJECT_ROOT,
        })
        elapsed = time.time() - start
        results.append((notebook_name, "SUCCESS", elapsed))
        print(f"  \u2713 Completed in {elapsed:.1f}s")
        if result:
            print(f"  Result: {result[:200]}")
    except Exception as e:
        elapsed = time.time() - start
        error_msg = str(e)[:300]
        results.append((notebook_name, "FAILED", elapsed))
        print(f"  \u2717 Failed after {elapsed:.1f}s")
        print(f"  Error: {error_msg}")
        raise RuntimeError(f"Deployment halted at '{notebook_name}': {error_msg}")

# COMMAND ----------

# DBTITLE 1,Deployment Summary
print("\n" + "=" * 60)
print("DEPLOYMENT SUMMARY")
print("=" * 60)

total_time = sum(t for _, _, t in results)
failed = [r for r in results if r[1] == "FAILED"]

for name, status, elapsed in results:
    icon = "\u2713" if status == "SUCCESS" else "\u2717"
    print(f"  {icon} {name:35s} {status:8s} ({elapsed:.1f}s)")

print(f"\nTotal time: {total_time:.1f}s")
print(f"Tables processed: {manifest.stats['total_tables']}")
print(f"Throughput: {manifest.stats['total_tables'] / max(total_time, 1):.1f} tables/sec")

all_passed = "ALL PASSED" if not failed else f"{len(failed)} FAILED"
print(f"Result: {all_passed}")

if not failed:
    dbutils.notebook.exit("SUCCESS")
else:
    dbutils.notebook.exit("FAILED")