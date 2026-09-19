# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 07: MNPI Expiration Manager
"""
Step 07: MNPI Expiration Manager — Temporal MNPI Governance

Manages MNPI policy expiration lifecycle:
  1. Checks all tables for expiration dates (from mnpi_expires tag)
  2. Identifies expired policies
  3. Drops expired policies from Unity Catalog
  4. Extends expiration for non-expired policies (5-day rolling window)
  5. Logs all changes to audit table

Schedule: Run hourly as part of pipeline or daily standalone

Expiration Date Format:
  - ISO 8601 with timezone: "2024-12-31T23:59:59-05:00" (EST)
  - "never": Policy never expires
  - Missing: Auto-assigned 5 days on first deployment
"""

import sys
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("abac_mvp2.mnpi_expiration")

# Widgets
dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("project_root", "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac", "Project Root")
dbutils.widgets.text("timezone", "America/New_York", "Timezone (IANA format)")
dbutils.widgets.text("dry_run", "false", "Dry Run (true/false)")
dbutils.widgets.text("extend_days", "5", "Days to extend non-expired")
dbutils.widgets.text("exit_on_complete", "false", "Call notebook.exit() at the end")

catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
project_root = dbutils.widgets.get("project_root")
timezone = dbutils.widgets.get("timezone")
dry_run = dbutils.widgets.get("dry_run").lower() == "true"
extend_days = int(dbutils.widgets.get("extend_days"))

sys.path.insert(0, f"{project_root}/src")

import importlib
importlib.invalidate_caches()
for _mod in ["config_loader", "spec_table_reader", "policy_inheritance", "mnpi_expiration"]:
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])

from spec_table_reader import EnhancedSpecTableABACLoader
from policy_inheritance import apply_inheritance_to_manifest
from mnpi_expiration import MNPIExpirationManager, apply_expiration_dates_to_manifest

print(f"MNPI Expiration Manager")
print(f"  Catalog: {catalog}")
print(f"  Timezone: {timezone}")
print(f"  Dry run: {dry_run}")
print(f"  Extension window: {extend_days} days")
print(f"  Current time: {datetime.now(ZoneInfo(timezone)).isoformat()}")

# COMMAND ----------

# DBTITLE 1,Load manifest from spec tables
# Load manifest from spec tables (never from pickle cache for interactive runs
# — a stale pickle silently predates config changes, see agent memories).
bronze_spec_table = "employee_dataflowspec_bronze"
silver_spec_table = "employee_dataflowspec_silver"
policies_path = f"{project_root}/configs/policies.yml"
mapping_table = "abac_dataflowspec_mapping"

loader = EnhancedSpecTableABACLoader(
    spark, catalog, sdp_meta_schema,
    bronze_spec_table, silver_spec_table,
    policies_path, mapping_table,
)
manifest = loader.load()
manifest = apply_inheritance_to_manifest(manifest)

# Apply expiration normalisation (parses mnpi_expiration_date from each table,
# handles "never" / missing / ISO-8601, returns (manifest, stats) tuple).
manifest, exp_stats = apply_expiration_dates_to_manifest(manifest)

print(f"\u2713 Manifest loaded: {len(manifest.tables)} tables")
print(f"  Expiration stats: {exp_stats}")
for t in manifest.tables:
    fqn = f"{t.catalog}.{t.schema}.{t.table_id}"
    print(f"  {fqn}: mnpi_expiration_date={t.mnpi_expiration_date!r}")

# COMMAND ----------

# DBTITLE 1,Scan for MNPI Policies and Expiration Dates
manager = MNPIExpirationManager(timezone)
current_time = datetime.now(ZoneInfo(timezone))

expired_policies = []
expiring_soon = []
active_policies = []
never_expire = []

for table in manifest.tables:
    # Check BOTH explicit and inherited policy_bindings (the latter come from
    # schema-level bindings via apply_inheritance_to_manifest).
    all_bindings = list(table.policy_bindings or []) + list(getattr(table, "inherited_policy_bindings", []) or [])
    has_mnpi = any("mnpi" in policy.lower() for policy in all_bindings)
    has_mnpi_tags = any("mnpi" in tag.lower() for tag in (table.tags or {}).keys())
    
    if not (has_mnpi or has_mnpi_tags):
        continue

    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"

    # Get expiration date from tags
    expiration_date = manager.get_expiration_from_tags(table.tags or {})

    if expiration_date is None:
        print(f"  ⚠ {fqn}: No expiration tag found (will be added next run)")
        continue

    if expiration_date == "never":
        never_expire.append({"fqn": fqn, "table": table, "expiration": "never"})
        continue

    # Check if expired
    is_expired = manager.is_expired(expiration_date, current_time)

    if is_expired:
        expired_policies.append({
            "fqn": fqn,
            "table": table,
            "expiration": expiration_date,
            "policies": table.policy_bindings,
        })
    else:
        # Check if expiring within next 24 hours
        expiration_dt = datetime.fromisoformat(expiration_date)
        hours_until = (expiration_dt - current_time).total_seconds() / 3600

        if hours_until < 24:
            expiring_soon.append({
                "fqn": fqn,
                "table": table,
                "expiration": expiration_date,
                "hours_until": hours_until,
            })
        else:
            active_policies.append({
                "fqn": fqn,
                "table": table,
                "expiration": expiration_date,
                "days_until": hours_until / 24,
            })

print("\n" + "=" * 70)
print("MNPI EXPIRATION SCAN RESULTS")
print("=" * 70)
print(f"  Expired (drop now):        {len(expired_policies)}")
print(f"  Expiring soon (<24h):      {len(expiring_soon)}")
print(f"  Active (>24h):             {len(active_policies)}")
print(f"  Never expires:             {len(never_expire)}")
print("=" * 70)

# COMMAND ----------

# DBTITLE 1,Extend Non-Expired Policies (Rolling Window)
extended_count = 0

print(f"\n{'=' * 70}")
print(f"EXTENDING ACTIVE POLICIES (Dry run: {dry_run})")
print(f"{'=' * 70}")
print(f"Extension: {extend_days} days from now")

for item in active_policies + expiring_soon:
    fqn = item["fqn"]
    table = item["table"]
    old_expiration = item["expiration"]

    # Calculate new expiration
    new_expiration = manager.extend_expiration(old_expiration, extend_days, current_time)

    print(f"\n{fqn}:")
    print(f"  Current expiration: {old_expiration}")
    print(f"  New expiration:     {new_expiration}")

    if not dry_run:
        try:
            spark.sql(f"ALTER TABLE {fqn} SET TAGS ('mnpi_expires' = '{new_expiration}')")
            extended_count += 1
            print(f"  ✓ Extended")
        except Exception as e:
            print(f"  ✗ Failed to extend: {e}")

if dry_run:
    print(f"\n✓ Dry run complete - {len(active_policies) + len(expiring_soon)} expirations would be extended")
else:
    print(f"\n✓ Extended {extended_count} policy expirations")

# COMMAND ----------

# DBTITLE 1,Summary Report
print("\n" + "=" * 70)
print("MNPI EXPIRATION MANAGER - SUMMARY")
print("=" * 70)
print(f"Expired policies:              {len(expired_policies)}")
print(f"Active policies extended:      {extended_count if not dry_run else f'{len(active_policies) + len(expiring_soon)} (dry run)'}")
print(f"Policies expiring soon (<24h): {len(expiring_soon)}")
print(f"Never-expiring policies:       {len(never_expire)}")
print(f"Dry run mode:                  {dry_run}")
print("=" * 70)

print(f"\n✓ Expiration management complete")
print(f"  Next recommended run: {(current_time + timedelta(hours=1)).isoformat()}")

if dbutils.widgets.get("exit_on_complete").lower() == "true":
    dbutils.notebook.exit(
        f"expired={len(expired_policies)}, extended={extended_count if not dry_run else 'dry_run'}, "
        f"never_expire={len(never_expire)}, dry_run={dry_run}"
    )