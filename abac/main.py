# Databricks notebook source
# MAGIC %md
# MAGIC # ABAC Governance Framework — Deployment Entry Point
# MAGIC
# MAGIC Orchestrates the full governance deployment pipeline (steps 02–06).
# MAGIC
# MAGIC | Step | Notebook | Purpose |
# MAGIC |------|----------|---------|
# MAGIC | 02 | apply_governed_tags | Apply class.* and custom tags to UC columns |
# MAGIC | 03 | deploy_masking_udfs | Deploy mask/filter UDFs to platform_admin schema |
# MAGIC | 04 | create_abac_policies | CREATE POLICY with MATCH COLUMNS for all bindings |
# MAGIC | 05 | validate_enforcement | Verify masking works at runtime |
# MAGIC | 06 | drift_detection | Check for drift between config and UC state |

# COMMAND ----------

import time

NOTEBOOK_DIR = "./src/notebooks"
TIMEOUT = 600  # 10 minutes per notebook

steps = [
    ("02_apply_governed_tags", "Apply governed tags to columns"),
    ("03_deploy_masking_udfs", "Deploy masking UDFs"),
    ("04_create_abac_policies", "Create ABAC policies"),
    ("05_validate_enforcement", "Validate enforcement"),
    ("06_drift_detection", "Run drift detection"),
]

print("ABAC Governance Deployment")
print("=" * 60)

# COMMAND ----------

results = []

for notebook_name, description in steps:
    path = f"{NOTEBOOK_DIR}/{notebook_name}"
    print(f"\n\u25b6 Step: {description}")
    print(f"  Notebook: {path}")

    start = time.time()
    try:
        result = dbutils.notebook.run(path, TIMEOUT)
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
        raise RuntimeError(
            f"Deployment halted at '{notebook_name}': {error_msg}"
        )

# COMMAND ----------

# MAGIC %md
# MAGIC ## Deployment Summary

# COMMAND ----------

print("\n" + "=" * 60)
print("DEPLOYMENT SUMMARY")
print("=" * 60)

total_time = sum(t for _, _, t in results)
failed = [r for r in results if r[1] == "FAILED"]

for name, status, elapsed in results:
    icon = "\u2713" if status == "SUCCESS" else "\u2717"
    print(f"  {icon} {name:30s} {status:8s} ({elapsed:.1f}s)")

print(f"\nTotal time: {total_time:.1f}s")
all_passed = "ALL PASSED" if not failed else f"{len(failed)} FAILED"
print(f"Result: {all_passed}")

if not failed:
    dbutils.notebook.exit("SUCCESS")
else:
    dbutils.notebook.exit("FAILED")