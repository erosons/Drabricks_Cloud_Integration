# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 04: Create ABAC Policies (Parallelized)
"""
Step 04: Create ABAC Policies — Scalable for 2000+ Tables

Reads policy_bindings from the multi-file securables config at SCHEMA and TABLE
levels, resolves {domain}_{layer} templates in principals/udf_bindings, and
generates CREATE OR REPLACE POLICY statements.

The SQL uses the Databricks ABAC CREATE POLICY syntax (requires Runtime 16.4+
or serverless compute):
  - ROW FILTER policies: WHEN has_tag(tag), USING COLUMNS for UDF args
  - COLUMN MASK policies: WHEN has_tag(tag), MATCH COLUMNS for tagged columns,
    ON COLUMN + USING COLUMNS for UDF args

ABACConfigLoader is NOT used: it is deliberately broken in this bundle.
Manifest is loaded from SDP-META spec tables -> UC Volume SecurableRegistry.
"""
import sys
import os
import yaml
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed

dbutils.widgets.text("project_root", "", "Project Root")
dbutils.widgets.text("use_cached_manifest", "false", "Use Cached Manifest (true/false)")
dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("bronze_spec_table", "employee_dataflowspec_bronze", "Bronze Spec Table")
dbutils.widgets.text("silver_spec_table", "employee_dataflowspec_silver", "Silver Spec Table")
dbutils.widgets.text("policies_path", "", "Policies Path (defaults to {project_root}/configs/policies.yml)")
dbutils.widgets.text("mapping_table", "abac_dataflowspec_mapping", "ABAC Mapping Table Name")
dbutils.widgets.text("dry_run", "true", "Dry run — preview SQL only (true) or execute (false)")
dbutils.widgets.text("exit_on_complete", "false", "Call notebook.exit() at the end (true for job runs)")

project_root = dbutils.widgets.get("project_root") or "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac"
use_cached_manifest = dbutils.widgets.get("use_cached_manifest").lower() == "true"
catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
bronze_spec_table = dbutils.widgets.get("bronze_spec_table")
silver_spec_table = dbutils.widgets.get("silver_spec_table")
mapping_table = dbutils.widgets.get("mapping_table")
policies_path = dbutils.widgets.get("policies_path") or f"{project_root}/configs/policies.yml"
dry_run = dbutils.widgets.get("dry_run").lower() == "true"
exit_on_complete = dbutils.widgets.get("exit_on_complete").lower() == "true"

sys.path.insert(0, f"{project_root}/src")

importlib.invalidate_caches()
for _mod in ["config_loader", "spec_table_reader", "policy_inheritance"]:
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])

from spec_table_reader import EnhancedSpecTableABACLoader
from policy_inheritance import apply_inheritance_to_manifest

print(f"Project root:  {project_root}")
print(f"Policies:      {policies_path}")
print(f"Catalog:       {catalog} | Spec schema: {sdp_meta_schema}")
print(f"Dry run:       {dry_run}")
print(f"Exit on complete: {exit_on_complete}")

# COMMAND ----------

# DBTITLE 1,Load manifest and build policy lookup
# Load manifest from spec tables (never from cache for interactive runs —
# a stale pickle silently predates config changes, see agent memories).
print(f"Loading governance manifest from spec tables: {catalog}.{sdp_meta_schema}")
loader = EnhancedSpecTableABACLoader(
    spark, catalog, sdp_meta_schema,
    bronze_spec_table, silver_spec_table,
    policies_path, mapping_table,
)
manifest = loader.load()
manifest = apply_inheritance_to_manifest(manifest)

print(f"Catalogs: {len(manifest.catalogs)}")
print(f"Schemas:  {len(manifest.schemas)}")
print(f"Tables:   {manifest.stats['total_tables']}")

# UDF location from policies.yml
udf_registry = manifest.policies["udf_registry"]
udf_prefix = f"{udf_registry['target_catalog']}.{udf_registry['target_schema']}"

# Build policy lookup: policy_id -> full definition (with policy_type tag)
policy_lookup = {}
for policy in manifest.policies.get("policies", {}).get("row_filters", []):
    policy_lookup[policy["policy_id"]] = {**policy, "policy_type": "row_filter"}
for policy in manifest.policies.get("policies", {}).get("column_masks", []):
    policy_lookup[policy["policy_id"]] = {**policy, "policy_type": "column_mask"}

# Build schema context: schema_id -> dict of ALL string-valued fields.
# Every string field in a schema's securables YAML entry automatically becomes
# a {key} placeholder available in policies.yml templates.  Adding a new field
# (e.g. productname, company, environment, application) to the securables YAML
# makes it instantly resolvable — no code change needed here.
schema_context = {}
for sch in manifest.schemas:
    sid = sch["schema_id"]
    ctx = {k: v for k, v in sch.items() if isinstance(v, str)}
    ctx.setdefault("catalog", catalog)       # always available
    ctx.setdefault("schema", sid)            # backward compat: {schema} -> schema_id
    schema_context[sid] = ctx

print(f"\nUDF location: {udf_prefix}")
print(f"Policy registry: {len(policy_lookup)} policies")
for pid, pdef in policy_lookup.items():
    print(f"  {pid} ({pdef['policy_type']}, scope={pdef['scope_level']}, "
          f"tag={pdef.get('table_tag')}, udf={pdef['udf']})")

print(f"\nSchema context (template variables):")
for sid, ctx in schema_context.items():
    display_keys = sorted(k for k in ctx if k not in ("catalog", "description"))
    print(f"  {sid}: {', '.join(f'{k}={ctx[k]}' for k in display_keys)}")

# COMMAND ----------

# DBTITLE 1,Collect policy bindings and resolve templates
# Walk all levels and collect bindings with domain/layer context for template
# resolution. Each binding is a dict so it can carry the resolved template
# variables alongside the scope/target/policy_id triple.
bindings = []
seen_bindings = set()

def add_binding(scope_type, target_fqn, policy_id, context=None):
    """Register a policy binding with its full schema context for template resolution."""
    key = (scope_type, target_fqn, policy_id)
    if key in seen_bindings:
        return
    seen_bindings.add(key)
    bindings.append({
        "scope_type": scope_type,
        "target_fqn": target_fqn,
        "policy_id": policy_id,
        "context": context or {},
    })

# 1. Catalog-level bindings (rare — most policies are schema-scoped)
for cat in manifest.catalogs:
    for policy_id in cat.get("policy_bindings", []):
        add_binding("CATALOG", cat["catalog_id"], policy_id)

# 2. Schema-level bindings — carry FULL schema context for template resolution
for sch in manifest.schemas:
    schema_fqn = f"{sch['catalog']}.{sch['schema_id']}"
    ctx = schema_context.get(sch["schema_id"], {})
    for policy_id in sch.get("policy_bindings", []):
        add_binding("SCHEMA", schema_fqn, policy_id, context=ctx)

# 3. Table-level bindings (ONLY explicit from table config files).
#    Do NOT include inherited_policy_bindings here — ABAC policies defined at
#    schema level already inherit to all child tables via the WHEN clause.
#    Creating a duplicate table-level policy would hit the "only one row filter
#    / column mask can resolve per table per user" limit.
for table in manifest.tables:
    table_fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    ctx = schema_context.get(table.schema, {})
    for policy_id in (getattr(table, "policy_bindings", []) or []):
        add_binding("TABLE", table_fqn, policy_id, context=ctx)

# Validate: every binding's policy_id must exist in policies.yml
missing_policies = [b for b in bindings if b["policy_id"] not in policy_lookup]
if missing_policies:
    print(f"\u26a0 {len(missing_policies)} binding(s) reference unknown policy_ids:")
    for b in missing_policies:
        print(f"    {b['scope_type']} {b['target_fqn']} <- {b['policy_id']}")

# Validate: schema/table bindings need at minimum domain+layer for template
# resolution.  Additional fields are optional — they only matter if the
# policies.yml templates reference them.
missing_ctx = [b for b in bindings
               if b["scope_type"] in ("SCHEMA", "TABLE")
               and (not b["context"].get("domain") or not b["context"].get("layer"))]
if missing_ctx:
    print(f"\u26a0 {len(missing_ctx)} binding(s) missing domain/layer in context:")
    for b in missing_ctx:
        print(f"    {b['scope_type']} {b['target_fqn']} <- {b['policy_id']}")

print(f"\nTotal policy bindings: {len(bindings)}")
print("=" * 60)
by_scope = {}
for b in bindings:
    by_scope.setdefault(b["scope_type"], []).append(b)

for scope, items in by_scope.items():
    print(f"  {scope}: {len(items)} bindings")
    for b in items[:5]:
        ctx = b.get("context", {})
        print(f"    {b['target_fqn']} <- {b['policy_id']} "
              f"[{ctx.get('domain')}/{ctx.get('layer')}]")
    if len(items) > 5:
        print(f"    ... and {len(items) - 5} more")

# COMMAND ----------

# DBTITLE 1,SQL builder for CREATE POLICY
import re as _re

def resolve_template(template_str, context):
    """Resolve {key} placeholders from a context dict.

    Every string-valued field in the schema's securables YAML entry is
    available as a {key} placeholder.  Adding a new field to the YAML
    (e.g. productname, company, environment, application) makes it
    instantly available in policies.yml templates — no code change needed.

    Unresolved placeholders remain as-is so they surface as a clear
    runtime error in the CREATE POLICY SQL rather than silently
    producing an empty string.
    """
    if not template_str or not isinstance(template_str, str):
        return template_str
    result = template_str
    for key, value in (context or {}).items():
        result = result.replace(f"{{{key}}}", value or "")
    return result


def build_create_policy_sql(binding, policy_def):
    """
    Generate CREATE OR REPLACE POLICY SQL from a policies.yml definition.

    Uses the Databricks ABAC CREATE POLICY syntax (Runtime 16.4+ / serverless):
      - ROW FILTER: WHEN has_tag(tag), USING COLUMNS for UDF args
      - COLUMN MASK: WHEN has_tag(tag), MATCH COLUMNS + ON COLUMN + USING COLUMNS

    Template resolution: {domain}_{layer} in principals and udf_bindings is
    resolved from the binding's domain/layer context (set per schema in the
    securables registry).
    """
    policy_id = binding["policy_id"]
    scope_type = binding["scope_type"]
    target_fqn = binding["target_fqn"]
    context = binding.get("context", {})
    policy_type = policy_def["policy_type"]
    udf_name = f"{udf_prefix}.{policy_def['udf']}"
    description = policy_def.get("description", "").replace("'", "''")
    table_tag = policy_def.get("table_tag")

    # Resolve ALL {key} placeholders in principals from the schema context
    to_principals = [
        f"`{resolve_template(p, context)}`"
        for p in policy_def.get("principals", {}).get("to", [])
    ]
    except_principals = [
        f"`{resolve_template(p, context)}`"
        for p in policy_def.get("principals", {}).get("except", [])
    ]

    # Resolve udf_bindings: {key} templates + special 'column_value'
    udf_bindings = policy_def.get("udf_bindings", {})
    resolved_bindings = {}
    for param, value in udf_bindings.items():
        resolved = resolve_template(value, context)
        resolved_bindings[param] = resolved

    # Build SQL
    lines = [f"CREATE OR REPLACE POLICY {policy_id}"]
    lines.append(f"ON {scope_type} {target_fqn}")
    lines.append(f"COMMENT '{description}'")

    if policy_type == "row_filter":
        lines.append(f"ROW FILTER {udf_name}")
    else:
        lines.append(f"COLUMN MASK {udf_name}")

    lines.append(f"TO {', '.join(to_principals)}")
    if except_principals:
        lines.append(f"EXCEPT {', '.join(except_principals)}")
    lines.append("FOR TABLES")

    # WHEN clause: match tables that carry the governed tag
    if table_tag:
        lines.append(f"WHEN has_tag('{table_tag}')")

    if policy_type == "row_filter":
        # Row filter: UDF takes only literal args (group_name) via USING COLUMNS.
        # filter_mnpi_access(group_name STRING) -> is_account_group_member(group_name)
        using_args = []
        for param in _udf_param_order(policy_def):
            val = resolved_bindings.get(param)
            if val and val != "column_value":
                using_args.append(f"'{val}'")
        if using_args:
            lines.append(f"USING COLUMNS ({', '.join(using_args)})")

    else:  # column_mask
        # Column mask: the masked column is identified via MATCH COLUMNS + ON COLUMN.
        # mask_mnpi_value(value STRING, group_name STRING)
        #   value       <- the tagged column (via ON COLUMN alias)
        #   group_name  <- literal string (via USING COLUMNS)
        if table_tag:
            lines.append(f"MATCH COLUMNS has_tag('{table_tag}') AS masked_col")
            lines.append("ON COLUMN masked_col")

        # USING COLUMNS: ON COLUMN already passes the column value as the
        # first UDF argument, so only include EXTRA literal bindings here.
        # Including the ON COLUMN alias again would double-count it.
        using_args = []
        for param in _udf_param_order(policy_def):
            val = resolved_bindings.get(param)
            if val == "column_value":
                continue  # ON COLUMN masked_col already provides this
            elif val:
                using_args.append(f"'{val}'")
        if using_args:
            lines.append(f"USING COLUMNS ({', '.join(using_args)})")

    return "\n".join(lines)


def _udf_param_order(policy_def):
    """Return UDF parameter names in declaration order from udf_registry."""
    udf_name = policy_def["udf"]
    for kind in ["row_filters", "column_masks"]:
        for entry in udf_registry.get(kind, []):
            if entry.get("function_id") == udf_name or entry.get("name") == udf_name:
                return [p["name"] for p in entry.get("parameters", [])]
    # Fallback: use udf_bindings key order
    return list((policy_def.get("udf_bindings") or {}).keys())


print("\u2713 SQL builder defined")

# COMMAND ----------

# DBTITLE 1,Preview generated SQL (always runs)
# Preview all generated SQL (always runs, regardless of dry_run)
print("GENERATED SQL STATEMENTS")
print("=" * 78)

generated_sql = []  # [(binding, sql_str)] for execution cell
skip_count = 0
error_count = 0

for b in bindings:
    pid = b["policy_id"]
    if pid not in policy_lookup:
        skip_count += 1
        continue

    policy_def = policy_lookup[pid]
    try:
        sql = build_create_policy_sql(b, policy_def)
        generated_sql.append((b, sql))
    except Exception as e:
        error_count += 1
        print(f"\n  \u2717 {pid} -> {b['target_fqn']}: {str(e)[:200]}")

for b, sql in generated_sql:
    pid = b["policy_id"]
    ptype = policy_lookup[pid]["policy_type"]
    print(f"\n  \u25b6 {pid} ({ptype}) -> {b['scope_type']} {b['target_fqn']}")
    ctx = b.get("context", {})
    print(f"    [{ctx.get('domain')}/{ctx.get('layer')}]")
    # Warn if any {key} placeholders survived resolution — means the
    # securables YAML is missing a field that policies.yml templates expect.
    unresolved = _re.findall(r'\{(\w+)\}', sql)
    if unresolved:
        print(f"    \u26a0 UNRESOLVED placeholders: {sorted(set(unresolved))}")
        print(f"      Add these fields to the schema in your securables YAML.")
        print(f"      Available context keys: {sorted(ctx.keys())}")
    print(f"  {'-' * 74}")
    for line in sql.split("\n"):
        print(f"    {line}")

print(f"\n{'=' * 78}")
print(f"  Generated: {len(generated_sql)} | Skipped (unknown policy): {skip_count} "
      f"| Build errors: {error_count}")
if dry_run:
    print("  Mode: DRY RUN \u2014 no policies will be created. Set dry_run=false to apply.")
else:
    print(f"  Mode: APPLY \u2014 {len(generated_sql)} CREATE POLICY statement(s) will execute next.")

# COMMAND ----------

# DBTITLE 1,Execute policies (gated by dry_run)
# Execute CREATE POLICY statements (gated by dry_run widget)
controls = getattr(manifest, "controls", None) or {}
max_workers = controls.get("reconciliation", {}).get("max_parallel_workers", 20)

deployed = []
failed = []

if dry_run:
    print("=" * 78)
    print("DRY RUN \u2014 no policies created.")
    print(f"  {len(generated_sql)} statement(s) would be executed.")
    print("  Set dry_run=false to apply.")
    print("=" * 78)
else:
    print(f"\nCreating {len(generated_sql)} ABAC policies "
          f"(max {max_workers} parallel)...")
    print("=" * 60)

    def create_policy(item):
        binding, sql = item
        try:
            spark.sql(sql)
            return ("success", binding["policy_id"], binding["target_fqn"], None)
        except Exception as e:
            return ("failed", binding["policy_id"], binding["target_fqn"],
                    str(e)[:300])

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(create_policy, item): item
                   for item in generated_sql}
        for future in as_completed(futures):
            status, pid, fqn, error = future.result()
            if status == "success":
                deployed.append(pid)
                print(f"  \u2713 {pid} -> {fqn}")
            else:
                failed.append((pid, fqn, error))
                print(f"  \u2717 {pid} -> {fqn}: {error[:120]}")

    print(f"\n{'=' * 60}")
    print(f"Deployed: {len(deployed)} | Failed: {len(failed)}")

# COMMAND ----------

# DBTITLE 1,Verify with SHOW POLICIES and summary
# Verify policies on each unique securable (only meaningful after execution)
print("\nVerification: SHOW POLICIES")
print("=" * 60)

checked = set()
for b in bindings:
    key = f"{b['scope_type']} {b['target_fqn']}"
    if key in checked:
        continue
    checked.add(key)

    try:
        result = spark.sql(
            f"SHOW POLICIES ON {b['scope_type']} {b['target_fqn']}"
        ).collect()
        if result:
            print(f"\n  {b['scope_type']} {b['target_fqn']}:")
            for row in result:
                print(f"    - {row['name']} ({row['type']})")
        else:
            print(f"\n  {b['scope_type']} {b['target_fqn']}: (no policies)")
    except Exception as e:
        print(f"\n  {b['scope_type']} {b['target_fqn']}: {str(e)[:80]}")

# Summary
print(f"\n{'=' * 60}")
print("ABAC POLICY SUMMARY")
print(f"{'=' * 60}")
print(f"  Bindings:    {len(bindings)}")
print(f"  Generated:   {len(generated_sql)}")
print(f"  Deployed:    {len(deployed)}")
print(f"  Failed:      {len(failed)}")
print(f"  Dry run:     {dry_run}")

if failed:
    print(f"\n\u2717 {len(failed)} policies failed:")
    for pid, fqn, err in failed:
        print(f"    - {pid} -> {fqn}: {err[:100]}")

summary = (
    f"generated={len(generated_sql)}, deployed={len(deployed)}, "
    f"failed={len(failed)}, dry_run={dry_run}"
)
print(f"\nSUMMARY: {summary}")

if exit_on_complete:
    dbutils.notebook.exit(summary)