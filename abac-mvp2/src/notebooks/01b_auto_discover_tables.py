# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %skip
# MAGIC import sys, os
# MAGIC
# MAGIC sys.path.append(
# MAGIC     os.path.abspath("/Workspace/abac-mvp2/src/config_loader")
# MAGIC )

# COMMAND ----------

# DBTITLE 1,Step 01b: Auto-Discover Tables
"""
Step 01b: Auto-Discover Tables from information_schema

Queries UC information_schema for tables matching auto_discover rules
that don't have explicit config files. Generates YAML config stubs
using the appropriate template.

This enables brownfield onboarding of 2000+ tables without manual config.
"""
import sys
import os

dbutils.widgets.text("config_path", "/Workspace/abac-mvp2/configs", "Config Directory")
dbutils.widgets.text("project_root", "", "Project Root")

config_path = dbutils.widgets.get("config_path") or "/Workspace/abac-mvp2/configs" or "/Workspace/abac-mvp2/configs"
project_root = dbutils.widgets.get("project_root") or "/Workspace/abac-mvp2"

sys.path.insert(0, f"{project_root}/src")
from config_loader import ABACConfigLoader, AutoDiscoveryEngine

print(f"Config path: {config_path}")
print(f"Project root: {project_root}")

# COMMAND ----------

# DBTITLE 1,Load manifest and discover
# Load the governance manifest
loader = ABACConfigLoader(config_path)
manifest = loader.load()

print(f"Currently managed tables: {manifest.stats['total_tables']}")
print(f"Auto-discover rules: {len(manifest.auto_discover_rules)}")
for rule in manifest.auto_discover_rules:
    print(f"  - {rule['catalog']}.{rule['schema']} -> template: {rule['apply_template']}")
    print(f"    Excludes: {rule.get('exclude_tables', [])}")

# COMMAND ----------

# DBTITLE 1,Discover unmanaged tables
# Run discovery against information_schema
engine = AutoDiscoveryEngine(manifest, spark)
unmanaged = engine.discover_unmanaged_tables()

print(f"\nDiscovered {len(unmanaged)} unmanaged tables:")
for t in unmanaged[:20]:  # Show first 20
    print(f"  - {t['fqn']} (template: {t['template']})")
if len(unmanaged) > 20:
    print(f"  ... and {len(unmanaged) - 20} more")

# COMMAND ----------

# DBTITLE 1,Generate config stubs
# Generate YAML config stubs for unmanaged tables
output_dir = os.path.join(config_path, "securables")
generated = engine.generate_config_stubs(output_dir)

print(f"\nGenerated {len(generated)} config stubs:")
for f in generated[:10]:
    print(f"  - {f}")
if len(generated) > 10:
    print(f"  ... and {len(generated) - 10} more")

print(f"\nConfig stubs are ready for review in: {output_dir}")
print("These will be picked up on the next deployment run.")

dbutils.notebook.exit(f"discovered={len(unmanaged)}, generated={len(generated)}")