# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 01b: Auto-Discover Tables
"""
Step 01b: Auto-Discover Tables from information_schema

Queries UC information_schema for tables that are covered by a schema-level
ABAC policy but are NOT enumerated in the SecurableRegistry YAML, then emits
v2-shaped config stubs for them.

This enables brownfield onboarding of large schemas without manual config.

SOURCE OF TRUTH: the same spec-table -> UC Volume registry path used by
notebook 01 (bronze_securables.yml / silver_securables.yml). The legacy
configs/securables/_templates_tags.yaml layout belongs to the standalone
abac_governance_mvp2 demo and does not exist in this bundle.
"""
import sys
import os
import importlib

dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("bronze_spec_table", "employee_dataflowspec_bronze", "Bronze Spec Table")
dbutils.widgets.text("silver_spec_table", "employee_dataflowspec_silver", "Silver Spec Table")
dbutils.widgets.text("project_root", "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac", "Project Root")
dbutils.widgets.text("policies_path", "", "Policies Path (defaults to {project_root}/configs/policies.yml)")
dbutils.widgets.text("use_mapping_table", "true", "Use ABAC Mapping Table (true/false)")
dbutils.widgets.text("mapping_table", "abac_dataflowspec_mapping", "ABAC Mapping Table Name")
dbutils.widgets.text("dry_run", "true", "Dry Run - report only, write no stubs (true/false)")
dbutils.widgets.text("output_root", "", "Stub Output Root (defaults to Volume conf/abac/discovered)")

catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
bronze_spec_table = dbutils.widgets.get("bronze_spec_table")
silver_spec_table = dbutils.widgets.get("silver_spec_table")
project_root = dbutils.widgets.get("project_root") or "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac"
policies_path = dbutils.widgets.get("policies_path") or f"{project_root}/configs/policies.yml"
use_mapping_table = dbutils.widgets.get("use_mapping_table").lower() == "true"
mapping_table = dbutils.widgets.get("mapping_table")
dry_run = dbutils.widgets.get("dry_run").lower() == "true"
output_root = dbutils.widgets.get("output_root") or (
    f"/Volumes/{catalog}/platform_admin/sdp_meta_files/conf/abac/discovered"
)

sys.path.insert(0, f"{project_root}/src")

# Modules under {project_root}/src stay cached in the REPL after being edited on
# disk; reload in dependency order (config_loader first) so ResolvedTable and
# GovernanceManifest come from the current source.
importlib.invalidate_caches()
for _mod in ["config_loader", "spec_table_reader", "policy_inheritance", "mnpi_expiration"]:
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])

from config_loader import AutoDiscoveryEngine
from spec_table_reader import SpecTableABACLoader, EnhancedSpecTableABACLoader

print(f"Project root: {project_root}")
print(f"Policies: {policies_path}")
print(f"Catalog: {catalog} | Spec schema: {sdp_meta_schema}")
print(f"Dry run: {dry_run}")
print(f"Stub output root: {output_root}")

# COMMAND ----------

# DBTITLE 1,Load registry manifest and derive auto-discover rules
# SDP-internal artifacts that are never governed securables
SDP_INTERNAL_EXCLUDES = ["__materialization_*", "event_log_*"]

# 1. Load the registry manifest via the same path notebook 01 uses
if use_mapping_table:
    loader = EnhancedSpecTableABACLoader(
        spark=spark,
        catalog=catalog,
        sdp_meta_schema=sdp_meta_schema,
        bronze_spec_table=bronze_spec_table,
        silver_spec_table=silver_spec_table,
        policies_path=policies_path,
        abac_mapping_table=mapping_table,
    )
else:
    loader = SpecTableABACLoader(
        spark=spark,
        catalog=catalog,
        sdp_meta_schema=sdp_meta_schema,
        bronze_spec_table=bronze_spec_table,
        silver_spec_table=silver_spec_table,
        policies_path=policies_path,
    )

manifest = loader.load()

# 2. Derive auto-discover rules from the TWO-TIER SCOPING MODEL.
#    A schema with NON-EMPTY policy_bindings has its policy applied ON SCHEMA,
#    so every table in it is governed - including tables never enumerated in
#    the YAML. Those are exactly the tables worth generating stubs for.
#    A schema with EMPTY policy_bindings delegates to its enumerated tables
#    only, so it is deliberately NOT a discovery target.
rules = []
for schema_config in manifest.schemas:
    bindings = list(schema_config.get("policy_bindings") or [])
    if not bindings:
        continue
    schema_id = schema_config.get("schema_id")
    rules.append({
        "catalog": schema_config.get("catalog", catalog),
        "schema": schema_id,
        "apply_template": f"inherit:{schema_id}",
        "policy_bindings": bindings,
        "exclude_tables": SDP_INTERNAL_EXCLUDES,
    })

manifest.auto_discover_rules = rules

print(f"Currently enumerated tables: {manifest.stats['total_tables']}")
for t in manifest.tables:
    print(f"  - {t.catalog}.{t.schema}.{t.table_id}")

print(f"\nAuto-discover rules: {len(manifest.auto_discover_rules)}")
for rule in manifest.auto_discover_rules:
    print(f"  - {rule['catalog']}.{rule['schema']} -> template: {rule['apply_template']}")
    print(f"    Schema-level bindings: {rule['policy_bindings']}")
    print(f"    Excludes: {rule.get('exclude_tables', [])}")

skipped = [s.get("schema_id") for s in manifest.schemas if not (s.get("policy_bindings") or [])]
if skipped:
    print(f"\nSkipped (empty policy_bindings, table-scoped only): {skipped}")

# COMMAND ----------

# DBTITLE 1,Discover unmanaged tables
# Run discovery against information_schema
# NOTE: the engine filters table_type IN ('MANAGED','EXTERNAL'), so SDP
# STREAMING_TABLE outputs are not reported as unmanaged here.
from collections import Counter

engine = AutoDiscoveryEngine(manifest, spark)
unmanaged = engine.discover_unmanaged_tables()

print(f"\nDiscovered {len(unmanaged)} unmanaged tables:")
for t in unmanaged[:20]:  # Show first 20
    print(f"  - {t['fqn']} (template: {t['template']})")
if len(unmanaged) > 20:
    print(f"  ... and {len(unmanaged) - 20} more")

if unmanaged:
    print("\nBy schema:")
    for schema_id, count in sorted(Counter(t["schema"] for t in unmanaged).items()):
        print(f"  {schema_id}: {count}")
else:
    print("\nNo unmanaged tables found - every table in the governed schemas is enumerated.")

# COMMAND ----------

# DBTITLE 1,Generate config stubs
# Generate v2 SecurableRegistry-shaped stubs for the discovered tables.
# The legacy engine.generate_config_stubs() writes the old flat .yaml shape
# into the bundle; this writes the registry shape (.yml) and records the
# schema-level bindings each table already inherits.
import yaml

rule_bindings = {
    (r["catalog"], r["schema"]): r["policy_bindings"]
    for r in manifest.auto_discover_rules
}


def build_stub(table_info):
    """v2 registry table entry for a discovered table."""
    inherited = rule_bindings.get((table_info["catalog"], table_info["schema"]), [])
    needs_masking = any("mask" in b.lower() for b in inherited)
    stub = {
        "table_id": table_info["table_id"],
        "description": f"Auto-discovered table: {table_info['fqn']}",
        # Empty: the schema-level policy already covers this table ON SCHEMA.
        # Add bindings here only to scope a policy ON TABLE instead.
        "policy_bindings": [],
        "tags": {},
        "grants": [],
    }
    if needs_masking:
        # Column masking requires either information_schema discovery or an
        # explicit mnpi_masked_columns list (engine errors without one).
        stub["information_schema"] = True
        stub["mnpi_expiration_date"] = None
    return stub, inherited


planned = []
for table_info in unmanaged:
    stub, inherited = build_stub(table_info)
    target = os.path.join(output_root, table_info["schema"], f"{table_info['table_id']}.yml")
    planned.append((target, stub, inherited, table_info))

generated = []
if dry_run:
    print(f"\nDRY RUN - would generate {len(planned)} config stubs (no files written).")
    for target, stub, inherited, _ in planned[:5]:
        print(f"\n  --> {target}")
        print(f"      inherits ON SCHEMA: {inherited}")
        for line in yaml.dump(stub, default_flow_style=False, sort_keys=False).splitlines():
            print(f"      {line}")
    if len(planned) > 5:
        print(f"\n  ... and {len(planned) - 5} more")
    print("\nSet dry_run=false to write these stubs.")
else:
    for target, stub, inherited, table_info in planned:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if os.path.exists(target):
            continue  # never clobber a reviewed config
        with open(target, "w") as f:
            f.write(f"# Auto-generated config for {table_info['fqn']}\n")
            f.write(f"# Covered ON SCHEMA by: {inherited}\n")
            f.write("# Review before merging into the SecurableRegistry.\n\n")
            yaml.dump(stub, f, default_flow_style=False, sort_keys=False)
        generated.append(target)

    print(f"\nGenerated {len(generated)} config stubs:")
    for f in generated[:10]:
        print(f"  - {f}")
    if len(generated) > 10:
        print(f"  ... and {len(generated) - 10} more")
    print(f"\nConfig stubs are ready for review in: {output_root}")
    print("Merge the reviewed entries into bronze/silver_securables.yml.")

dbutils.notebook.exit(
    f"discovered={len(unmanaged)}, planned={len(planned)}, generated={len(generated)}, dry_run={dry_run}"
)