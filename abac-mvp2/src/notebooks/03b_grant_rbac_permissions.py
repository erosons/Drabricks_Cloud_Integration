# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 03b: Grant RBAC Permissions (Parallel)
"""
Step 03b: Grant RBAC Permissions — Parallelized for 2000+ tables

Establishes base RBAC grants defined in the multi-file securables config
BEFORE ABAC policies are applied.

ABAC policies (row filters, column masks) do NOT grant access — they only
restrict what's visible once a user already has access. This notebook ensures
the prerequisite RBAC grants exist so that ABAC `TO` groups can query objects.

Logic:
1. Load manifest (multi-file configs + templates)
2. Route privileges to the correct securable level (CATALOG/SCHEMA/TABLE)
3. Build deduplicated grant plan
4. Execute grants in parallel batches
5. Verify with SHOW GRANTS
"""
import sys
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

dbutils.widgets.text("config_path", "", "Config Directory")
dbutils.widgets.text("project_root", "", "Project Root")

config_path = dbutils.widgets.get("config_path") or "/Workspace/abac-mvp2/configs" or "/Workspace/abac-mvp2/configs"
project_root = dbutils.widgets.get("project_root") or "/Workspace/abac-mvp2"

sys.path.insert(0, f"{project_root}/src")
from config_loader import ABACConfigLoader

print(f"Config path: {config_path}")

# COMMAND ----------

# DBTITLE 1,Load manifest and define privilege routing
# Load governance manifest
loader = ABACConfigLoader(config_path)
manifest = loader.load()

print(f"Catalogs: {len(manifest.catalogs)}")
print(f"Schemas:  {len(manifest.schemas)}")
print(f"Tables:   {manifest.stats['total_tables']}")

# Privilege routing — determines which securable level a privilege applies to
CATALOG_ONLY_PRIVS = {"USE CATALOG", "BROWSE SCHEMA"}
SCHEMA_ONLY_PRIVS = {"USE SCHEMA", "CREATE TABLE", "CREATE FUNCTION", "CREATE VOLUME"}
TABLE_PRIVS = {"SELECT", "MODIFY", "APPLY TAG", "INSERT", "UPDATE", "DELETE"}
# Flexible privileges get routed to the highest level specified
FLEXIBLE_PRIVS = {"BROWSE"}

def route_privilege(priv, securable_level):
    """Determine the correct ON clause for a privilege."""
    priv_upper = priv.strip().upper()
    if priv_upper in CATALOG_ONLY_PRIVS:
        return "catalog"
    elif priv_upper in SCHEMA_ONLY_PRIVS:
        return "schema"
    elif priv_upper in TABLE_PRIVS:
        return securable_level  # TABLE or SCHEMA depending on source
    elif priv_upper in FLEXIBLE_PRIVS:
        return securable_level
    else:
        return securable_level

print("\u2713 Privilege routing logic defined")

# COMMAND ----------

# DBTITLE 1,Build grant plan from all levels
# Build a deduplicated grant plan
# Format: set of (sql_statement, description) tuples
grant_plan = []
seen_grants = set()

def add_grant(priv_list, on_type, on_fqn, group, source_desc):
    """Add a GRANT statement to the plan, deduplicating."""
    if not priv_list:
        return
    # Route privileges to correct level
    routed = {}  # {level: [privs]}
    for p in priv_list:
        level = route_privilege(p, on_type.lower())
        routed.setdefault(level, []).append(p)

    for level, privs in routed.items():
        priv_str = ", ".join(privs)
        if level == "catalog":
            # Extract catalog from fqn
            catalog = on_fqn.split(".")[0]
            sql = f"GRANT {priv_str} ON CATALOG `{catalog}` TO `{group}`"
        elif level == "schema":
            parts = on_fqn.split(".")
            schema_fqn = ".".join(parts[:2]) if len(parts) >= 2 else on_fqn
            sql = f"GRANT {priv_str} ON SCHEMA `{'`.`'.join(schema_fqn.split('.'))}` TO `{group}`"
        else:  # table
            sql = f"GRANT {priv_str} ON TABLE `{'`.`'.join(on_fqn.split('.'))}` TO `{group}`"

        if sql not in seen_grants:
            seen_grants.add(sql)
            grant_plan.append((sql, source_desc))

# 1. Catalog-level grants
for cat in manifest.catalogs:
    catalog_id = cat["catalog_id"]
    for grant in cat.get("grants", []):
        group = grant["group"]
        add_grant(grant["privileges"], "CATALOG", catalog_id, group,
                  f"CATALOG {catalog_id} -> {group}")

# 2. Schema-level grants
for sch in manifest.schemas:
    schema_fqn = f"{sch['catalog']}.{sch['schema_id']}"
    for grant in sch.get("grants", []):
        group = grant["group"]
        add_grant(grant["privileges"], "SCHEMA", schema_fqn, group,
                  f"SCHEMA {schema_fqn} -> {group}")

# 3. Table-level grants (from resolved configs)
for table in manifest.tables:
    table_fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    for grant in table.grants:
        group = grant.get("group", grant.get("role", ""))
        privs = grant.get("privileges", [])
        if privs:
            add_grant(privs, "TABLE", table_fqn, group,
                      f"TABLE {table_fqn} -> {group}")

print(f"\nGrant plan: {len(grant_plan)} unique statements")
print("=" * 60)
for sql, desc in grant_plan[:20]:
    print(f"  {desc}")
if len(grant_plan) > 20:
    print(f"  ... and {len(grant_plan) - 20} more")

# COMMAND ----------

# DBTITLE 1,Execute grants in parallel
# Execute all GRANT statements in parallel
max_workers = manifest.controls.get("reconciliation", {}).get("max_parallel_workers", 20)

granted = []
failed = []

print(f"\nApplying {len(grant_plan)} RBAC grants (max {max_workers} parallel)...")
print("=" * 60)

def execute_grant(item):
    sql, desc = item
    try:
        spark.sql(sql)
        return ("success", sql, desc, None)
    except Exception as e:
        return ("failed", sql, desc, str(e)[:200])

with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(execute_grant, item): item for item in grant_plan}
    for future in as_completed(futures):
        status, sql, desc, error = future.result()
        if status == "success":
            granted.append(desc)
            print(f"  \u2713 {desc}")
        else:
            failed.append((desc, error))
            print(f"  \u2717 {desc}: {error[:100]}")

print(f"\n{'=' * 60}")
print(f"Executed: {len(granted)} | Failed: {len(failed)}")

# COMMAND ----------

# DBTITLE 1,Verify grants and summary
# Verify grants on primary securables
print("\nVerification: Checking grants on primary securables")
print("=" * 60)

verification_targets = []
for cat in manifest.catalogs:
    verification_targets.append(("CATALOG", cat["catalog_id"]))
for sch in manifest.schemas:
    verification_targets.append(("SCHEMA", f"{sch['catalog']}.{sch['schema_id']}"))

for scope_type, fqn in verification_targets:
    try:
        result = spark.sql(f"SHOW GRANTS ON {scope_type} {fqn}").collect()
        if result:
            print(f"\n  {scope_type} {fqn} ({len(result)} grant entries):")
            for row in result[:5]:
                print(f"    {row['Principal']:40s} {row['ActionType']}")
            if len(result) > 5:
                print(f"    ... and {len(result) - 5} more")
    except Exception as e:
        print(f"\n  {scope_type} {fqn}: {str(e)[:80]}")

# Summary
print(f"\n{'=' * 60}")
print("RBAC GRANT SUMMARY")
print(f"{'=' * 60}")
print(f"  Total planned:  {len(grant_plan)}")
print(f"  Executed:       {len(granted)}")
print(f"  Failed:         {len(failed)}")
print(f"  Tables covered: {manifest.stats['total_tables']}")

if failed:
    print(f"\n\u26a0 Failures (may require elevated privileges):")
    for desc, err in failed[:10]:
        print(f"    - {desc}: {err[:80]}")

dbutils.notebook.exit(f"granted={len(granted)}, failed={len(failed)}")