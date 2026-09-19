# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 02: Apply Governed Tags (Parallel)
"""
Step 02: Apply Governed Tags — Parallelized for 2000+ tables

0. Ensure the governed tags declared in policies.yml exist in the account
1. Load manifest from the SDP-META spec tables -> UC Volume SecurableRegistry
2. Preflight the declared governed tags against the account tag policies
3. Apply SCHEMA-level and TABLE-level governed tags in parallel batches
4. Log results for audit trail

TAG SCOPE: policies.yml declares mnpi_row_filtered / mnpi_column_masked with
`scope: table`, and the registry carries them as schema-level and table-level
`tags:` maps. Tags are therefore applied with ALTER TABLE / ALTER SCHEMA ...
SET TAGS, NOT as column tags. The old TemplateResolver column-pattern path is
not used: the spec-table manifest is built with templates={}, so pattern
matching resolved zero tags for every column.

ABACConfigLoader is also not used - it hardcodes 'policies.yaml' (file is
'policies.yml') and expects a configs/securables/ tree that does not exist in
this bundle, so .load() raises FileNotFoundError.
"""
import sys
import os
import re
import logging
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("abac_mvp2.apply_tags")

dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("bronze_spec_table", "employee_dataflowspec_bronze", "Bronze Spec Table")
dbutils.widgets.text("silver_spec_table", "employee_dataflowspec_silver", "Silver Spec Table")
dbutils.widgets.text("project_root", "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac", "Project Root")
dbutils.widgets.text("policies_path", "", "Policies Path (defaults to {project_root}/configs/policies.yml)")
dbutils.widgets.text("use_mapping_table", "true", "Use ABAC Mapping Table (true/false)")
dbutils.widgets.text("mapping_table", "abac_dataflowspec_mapping", "ABAC Mapping Table Name")
dbutils.widgets.text("use_cached_manifest", "false", "Use Cached Manifest (true/false)")
dbutils.widgets.text("dry_run", "false", "Dry Run - report only, apply no tags (true/false)")
dbutils.widgets.text("exit_on_complete", "false", "Call notebook.exit() at the end (true for job runs)")
dbutils.widgets.text("ensure_governed_tags", "true", "Create missing governed tags from policies.yml (true/false)")

catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
bronze_spec_table = dbutils.widgets.get("bronze_spec_table")
silver_spec_table = dbutils.widgets.get("silver_spec_table")
project_root = dbutils.widgets.get("project_root") or "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac"
policies_path = dbutils.widgets.get("policies_path") or f"{project_root}/configs/policies.yml"
use_mapping_table = dbutils.widgets.get("use_mapping_table").lower() == "true"
mapping_table = dbutils.widgets.get("mapping_table")
use_cached_manifest = dbutils.widgets.get("use_cached_manifest").lower() == "true"
dry_run = dbutils.widgets.get("dry_run").lower() == "true"
# dbutils.notebook.exit() discards everything a cell printed, so it is opt-in:
# interactive runs keep the full audit trail, job runs can still return a value.
exit_on_complete = dbutils.widgets.get("exit_on_complete").lower() == "true"
# Stage 0 below creates any declared-but-missing account tag policy, so that the
# tags applied later are GOVERNED rather than free-form.
ensure_governed_tags = dbutils.widgets.get("ensure_governed_tags").lower() == "true"

sys.path.insert(0, f"{project_root}/src")

# Modules under {project_root}/src stay cached in the REPL after being edited on
# disk; reload in dependency order (config_loader first) so ResolvedTable and
# GovernanceManifest come from the current source.
importlib.invalidate_caches()
for _mod in ["config_loader", "spec_table_reader", "policy_inheritance", "mnpi_expiration"]:
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])

from config_loader import ParallelGovernanceExecutor, ResolvedTable
from spec_table_reader import SpecTableABACLoader, EnhancedSpecTableABACLoader
from policy_inheritance import apply_inheritance_to_manifest
from mnpi_expiration import apply_expiration_dates_to_manifest

print(f"Project root: {project_root}")
print(f"Policies:     {policies_path}")
print(f"Catalog:      {catalog} | Spec schema: {sdp_meta_schema}")
print(f"Dry run:      {dry_run}")
print(f"Exit on complete: {exit_on_complete}")
print(f"Ensure governed tags: {ensure_governed_tags}")

# COMMAND ----------

# DBTITLE 1,Stage 0: Ensure governed tags exist
"""
STAGE 0: Reconcile declared governed tags against the account (runs BEFORE any
tag is applied).

policies.yml `governed_tags` is the declaration of intent. Governed tags are
ACCOUNT-level tag policies and CANNOT be created in SQL - only via Catalog
Explorer > Govern > Governed Tags, the CLI, or tag_policies.create_tag_policy().
This stage creates whatever is declared but missing, so the tags applied later
in this notebook are GOVERNED rather than free-form.

Why this matters: a free-form tag can be set or removed by anyone holding
APPLY TAG on the object, so an owner could silently drop their table out of an
MNPI policy's scope. A governed tag requires ASSIGN on the tag itself, which
separates 'who owns the table' from 'who may classify it as MNPI'.

VALUE SEMANTICS (verified the hard way): an EMPTY allowed-values list does NOT
mean 'any value'. It means PRESENCE-ONLY - the tag accepts only an empty value,
and any non-empty value is rejected with
  INVALID_PARAMETER_VALUE ... is not an allowed value for tag policy key <key>
So a governed tag can hold either an enumerated value or nothing at all; it can
NEVER hold an unbounded value such as a timestamp.

Consequence: only tags that are actually referenced by an ABAC policy (non-empty
`used_by_policies`) or that declare `allowed_values` are governed here. A tag
like `mnpi_expires`, which carries an arbitrary ISO timestamp and drives no
policy, is operational metadata and is intentionally left free-form - governing
it would make every ALTER ... SET TAGS call fail.
"""
import yaml
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.tags import TagPolicy, Value

with open(policies_path, "r") as f:
    _policies_doc = yaml.safe_load(f) or {}

declared_tags = _policies_doc.get("governed_tags", []) or []
if not declared_tags:
    raise ValueError(f"No 'governed_tags' section declared in {policies_path}")

w_tags = WorkspaceClient()

print(f"Declared governed tags in {os.path.basename(policies_path)}: {len(declared_tags)}")
print("=" * 60)

tag_state = {}
create_failures = []
# key -> allowed value list, for every tag that IS governed in the account.
# Consumed by the apply stage to pre-validate values before issuing SET TAGS.
governed_tag_allowed = {}
free_form_by_design = []

for tag_def in declared_tags:
    key = tag_def["key"]
    description = tag_def.get("description", "")
    allowed_values = tag_def.get("allowed_values") or []
    # Govern only what a policy actually evaluates, or what declares a value set.
    should_govern = bool(tag_def.get("used_by_policies")) or bool(allowed_values)

    # 1. Already present in the account?
    try:
        existing = w_tags.tag_policies.get_tag_policy(tag_key=key)
        existing_values = [v.name for v in existing.values] if existing.values else []
        governed_tag_allowed[key] = existing_values
        tag_state[key] = "existing"
        print(f"  EXISTS   {key} (allowed: {existing_values or 'presence-only'})")
        if allowed_values and sorted(existing_values) != sorted(allowed_values):
            print(f"           DRIFT: policies.yml declares {sorted(allowed_values)}")
        if not should_govern:
            print(f"           WARNING: {key} drives no policy and declares no")
            print(f"           allowed_values, but a tag policy exists. Any non-empty")
            print(f"           value for it will be REJECTED on assignment. Delete the")
            print(f"           tag policy to return it to free-form.")
        continue
    except Exception:
        pass  # not found -> fall through to create

    if not should_govern:
        free_form_by_design.append(key)
        tag_state[key] = "free_form_by_design"
        print(f"  SKIP     {key} - drives no policy, carries free-form values")
        continue

    if not ensure_governed_tags:
        tag_state[key] = "missing"
        print(f"  MISSING  {key} - ensure_governed_tags=false, not creating")
        continue

    # 2. Create it. values=None means the tag accepts any value.
    try:
        w_tags.tag_policies.create_tag_policy(
            tag_policy=TagPolicy(
                tag_key=key,
                description=description,
                values=[Value(name=v) for v in allowed_values] or None,
            )
        )
        tag_state[key] = "created"
        governed_tag_allowed[key] = allowed_values
        print(f"  CREATED  {key} (allowed: {allowed_values or 'presence-only'})")
    except Exception as e:
        tag_state[key] = "failed"
        create_failures.append((key, f"{type(e).__name__}: {str(e)[:200]}"))
        print(f"  FAILED   {key}: {type(e).__name__}: {str(e)[:200]}")

# 3. Re-verify against the account instead of trusting the create calls
print("\nRE-VERIFICATION")
print("=" * 60)
governed_now, still_ungoverned = [], []
for tag_def in declared_tags:
    key = tag_def["key"]
    try:
        w_tags.tag_policies.get_tag_policy(tag_key=key)
        governed_now.append(key)
        print(f"  GOVERNED   {key}")
    except Exception:
        still_ungoverned.append(key)
        print(f"  FREE-FORM  {key}")

print(f"\nGoverned: {len(governed_now)}/{len(declared_tags)}")
if free_form_by_design:
    print(f"Free-form by design: {free_form_by_design}")

if create_failures:
    print("\nCreation failures:")
    for key, err in create_failures:
        print(f"  - {key}: {err}")
    print("  Creating a governed tag requires account admin or MANAGE on the account.")
    print("  UI alternative: Catalog Explorer > Govern > Governed Tags > Create Governed Tag.")

if governed_now:
    print("\nNOTE: assigning a governed tag requires ASSIGN on the tag policy PLUS")
    print("  APPLY TAG on the target object. If the ALTER ... SET TAGS calls later in")
    print("  this notebook begin failing with a permission error, grant ASSIGN to the")
    print("  principal running it - including the run_all_pipelines service principal.")

# COMMAND ----------

# DBTITLE 1,Load manifest and validate tags
# Load manifest - either from cache or from disk
import pickle
import base64

manifest = None

if use_cached_manifest:
    print("Loading manifest from cache...")
    # Try task values first
    try:
        manifest_b64 = dbutils.jobs.taskValues.get(taskKey="apply_abac_governance", key="manifest", debugValue=None)
        if manifest_b64:
            manifest_bytes = base64.b64decode(manifest_b64)
            manifest = pickle.loads(manifest_bytes)
            print("✓ Loaded manifest from job task values")
    except Exception as e:
        print(f"⚠ Could not load from task values: {e}")

    # Fallback: Load from temp table
    if manifest is None:
        temp_table = f"{catalog}.{sdp_meta_schema}.manifest_cache"
        print(f"⚠ Falling back to temp table: {temp_table}")
        try:
            manifest_df = spark.sql(f"SELECT manifest_json FROM {temp_table} ORDER BY loaded_at DESC LIMIT 1")
            manifest_row = manifest_df.first()
            if manifest_row:
                manifest_bytes = base64.b64decode(manifest_row.manifest_json)
                manifest = pickle.loads(manifest_bytes)
                print(f"✓ Loaded manifest from temp table")
        except Exception as e:
            print(f"✗ Failed to load from temp table: {e}")
            raise

if manifest is None:
    print(f"Loading governance manifest from spec tables: {catalog}.{sdp_meta_schema}")
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

    # Resolve the two-tier model (populates inherited_policy_bindings), then
    # stamp mnpi_expires into table.tags so it is applied with the other tags.
    manifest = apply_inheritance_to_manifest(manifest)
    manifest, expiration_stats = apply_expiration_dates_to_manifest(manifest)
    print(f"  MNPI expiration stats: {expiration_stats}")

# Extract governed tag keys from policies
policy_tag_keys = set()
for tag_def in manifest.policies.get("governed_tags", []):
    policy_tag_keys.add(tag_def["key"])

print(f"Governed tags declared in policies: {len(policy_tag_keys)}")
for key in sorted(policy_tag_keys):
    print(f"  - {key}")

# PREFLIGHT: governed tags CANNOT be created with SQL - they are account-level
# tag policies created via Catalog Explorer > Govern, the SDK, or the CLI.
# If a declared key has no tag policy, the ALTER ... SET TAGS calls below still
# succeed but produce a FREE-FORM tag, and ABAC policies in notebook 04 that
# reference that tag will not resolve against it.
print("\nGoverned tag preflight (account tag policies):")
ungoverned = []
try:
    from databricks.sdk import WorkspaceClient
    _w = WorkspaceClient()
    for key in sorted(policy_tag_keys):
        try:
            _pol = _w.tag_policies.get_tag_policy(tag_key=key)
            _allowed = [v.name for v in _pol.values] if _pol.values else []
            print(f"  GOVERNED   {key} (allowed: {_allowed or 'presence-only'})")
        except Exception:
            ungoverned.append(key)
            print(f"  FREE-FORM  {key} - no account tag policy exists")
except Exception as e:
    print(f"  (could not query account tag policies: {e})")

if ungoverned:
    print(f"\nWARNING: {len(ungoverned)} declared tag(s) are NOT governed: {ungoverned}")
    print("  policies.yml marks these 'source: workspace_existing', but no account")
    print("  tag policy exists for them. They will be applied as free-form tags.")
    print("  An account admin must create them before notebook 04's ABAC policies")
    print("  can resolve: Catalog Explorer > Govern > Governed Tags, or the")
    print("  w.tag_policies.create_tag_policy() SDK call.")

print(f"\nTables to process: {manifest.stats['total_tables']}")
schemas_with_tags = [s for s in manifest.schemas if s.get("tags")]
print(f"Schemas with tags:  {len(schemas_with_tags)} "
      f"({', '.join(s.get('schema_id', '?') for s in schemas_with_tags) or 'none'})")
tables_with_tags = [t for t in manifest.tables if t.tags]
print(f"Tables with tags:   {len(tables_with_tags)}")
for t in tables_with_tags:
    print(f"  - {t.catalog}.{t.schema}.{t.table_id}: {t.tags}")

# COMMAND ----------

# DBTITLE 1,Define tag application operation
def filter_declared(tags):
    """Keep only tags declared in policies.yml governed_tags, as strings."""
    return {
        k: ("" if v is None else str(v))
        for k, v in (tags or {}).items()
        if k in policy_tag_keys
    }


def tag_value_allowed(key, value):
    """
    Check a value against the governed tag policy BEFORE issuing SET TAGS.

    A governed tag with an empty allowed-values list is presence-only: it accepts
    only an empty value. With a non-empty list, the value must be a member.
    Free-form tags (no tag policy) accept anything.
    """
    if key not in governed_tag_allowed:
        return True, None
    allowed = governed_tag_allowed[key]
    if not allowed:
        if value == "":
            return True, None
        return False, (f"governed tag '{key}' is presence-only; value "
                       f"{value!r} would be rejected")
    if value in allowed:
        return True, None
    return False, (f"governed tag '{key}' allows {allowed}; value "
                   f"{value!r} would be rejected")


def apply_tags_to_table(spark_session, table: ResolvedTable):
    """
    Apply governed tags to a single TABLE (not to its columns).

    policies.yml declares mnpi_row_filtered / mnpi_column_masked with
    `scope: table`, and the registry carries them in each table's `tags:` map,
    so this issues one ALTER TABLE ... SET TAGS. Column-level tagging via
    template patterns is not used - see the note in cell 1.
    """
    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"

    # 1. Confirm the table exists - the SDP pipeline may not have created it yet
    try:
        exists = spark_session.sql(f"""
            SELECT 1
            FROM {table.catalog}.information_schema.tables
            WHERE table_schema = '{table.schema}'
              AND table_name = '{table.table_id}'
            LIMIT 1
        """).collect()
    except Exception as e:
        return {"status": "failed", "error": f"Cannot check table existence: {e}"}

    if not exists:
        return {"status": "skipped", "reason": "table does not exist yet"}

    # 2. Only apply tags declared in policies.yml governed_tags
    declared = filter_declared(table.tags)
    undeclared = sorted(set(table.tags or {}) - set(declared))

    if not declared:
        return {
            "status": "skipped",
            "reason": "no declared tags on this table",
            "tags_skipped": len(undeclared),
            "undeclared": undeclared,
        }

    # 3. Drop values a governed tag policy would reject, so one bad value cannot
    #    block the rest. (A single multi-tag SET TAGS is atomic: when mnpi_expires
    #    was governed presence-only, its timestamp took the classification flags
    #    down with it and all 4 tables failed.)
    appliable, blocked = {}, []
    for k, v in declared.items():
        ok, reason = tag_value_allowed(k, v)
        if ok:
            appliable[k] = v
        else:
            blocked.append({"tag": k, "value": v, "reason": reason})

    if not appliable:
        return {
            "status": "skipped",
            "reason": "every declared tag value was rejected by its tag policy",
            "blocked": blocked,
            "tags_skipped": len(undeclared),
        }

    if dry_run:
        return {
            "status": "success",
            "tags_applied": 0,
            "tags_planned": len(appliable),
            "planned": appliable,
            "blocked": blocked,
            "tags_skipped": len(undeclared),
        }

    # 4. One statement per tag, so a rejection is isolated to that tag
    applied, errors = {}, []
    for k, v in appliable.items():
        sql = f"ALTER TABLE {fqn} SET TAGS ('{k}' = '{v}')"
        try:
            spark_session.sql(sql)
            applied[k] = v
        except Exception as e:
            errors.append({"tag": k, "error": f"{type(e).__name__}: {str(e)[:160]}"})

    if errors and not applied:
        return {
            "status": "failed",
            "error": "; ".join(f"{e['tag']}: {e['error']}" for e in errors),
            "blocked": blocked,
        }

    return {
        "status": "success",
        "tags_applied": len(applied),
        "applied": applied,
        "errors": errors,
        "blocked": blocked,
        "tags_skipped": len(undeclared),
        "undeclared": undeclared,
    }

# COMMAND ----------

# DBTITLE 1,Execute tag application in parallel batches
# 1. SCHEMA-level tags first. ABAC treats a schema tag as inherited by every
#    table in that schema, which is how the hr schema (20 tables, none of them
#    enumerated in the registry) gets covered without per-table tagging.
print("SCHEMA-LEVEL TAGS")
print("=" * 60)
schema_tags_applied = 0
schema_failures = []

for schema_config in manifest.schemas:
    declared = filter_declared(schema_config.get("tags"))
    if not declared:
        continue
    sfqn = f"{schema_config.get('catalog', catalog)}.{schema_config.get('schema_id')}"
    tag_pairs = ", ".join(f"'{k}' = '{v}'" for k, v in declared.items())
    sql = f"ALTER SCHEMA {sfqn} SET TAGS ({tag_pairs})"

    if dry_run:
        print(f"  DRY RUN {sfqn}: {declared}")
        continue
    try:
        spark.sql(sql)
        schema_tags_applied += len(declared)
        print(f"  OK      {sfqn}: {declared}")
    except Exception as e:
        schema_failures.append((sfqn, str(e)[:200]))
        print(f"  FAILED  {sfqn}: {str(e)[:200]}")

if schema_tags_applied == 0 and not dry_run and not schema_failures:
    print("  (no schema carries a declared tag)")

# 2. TABLE-level tags in parallel batches
print("\nTABLE-LEVEL TAGS")
print("=" * 60)
executor = ParallelGovernanceExecutor(spark, manifest)
results = executor.execute_in_batches(
    manifest.tables,
    apply_tags_to_table,
    operation_name="apply_governed_tags",
)

print("\n" + "=" * 60)
print("TAG APPLICATION RESULTS")
print("=" * 60)
print(f"  Total tables:  {results['total']}")
print(f"  Success:       {results['success']}")
print(f"  Failed:        {results['failed']}")
print(f"  Skipped:       {results['skipped']}")

# Aggregate tag counts
tag_field = "tags_planned" if dry_run else "tags_applied"
total_tags = sum(
    d.get(tag_field, 0)
    for d in results["details"] if d.get("status") == "success"
)
print(f"  Schema tags:   {schema_tags_applied}")
print(f"  Table tags:    {total_tags}{' (planned)' if dry_run else ''}")

for d in results["details"]:
    if d.get("status") == "skipped":
        print(f"  SKIPPED {d['fqn']}: {d.get('reason')}")

# Values a governed tag policy refuses - reported, never silently dropped
blocked_all = [(d["fqn"], b) for d in results["details"] for b in d.get("blocked", [])]
if blocked_all:
    print(f"\n  Blocked by tag policy: {len(blocked_all)}")
    for fqn, b in blocked_all:
        print(f"    {fqn}: {b['reason']}")

partial = [(d["fqn"], e) for d in results["details"] for e in d.get("errors", [])]
if partial:
    print(f"\n  Per-tag errors: {len(partial)}")
    for fqn, e in partial:
        print(f"    {fqn}: {e['tag']} -> {e['error']}")

if results['failed'] > 0:
    print("\nFailed tables:")
    for d in results["details"]:
        if d.get("status") in ("failed", "error"):
            print(f"  - {d['fqn']}: {d.get('error', 'unknown')}")

# 3. Verify what actually landed in Unity Catalog, rather than trusting the
#    per-statement return codes.
if not dry_run:
    print("\nVERIFICATION (system.information_schema)")
    print("=" * 60)
    key_list = ", ".join(f"'{k}'" for k in sorted(policy_tag_keys)) or "''"

    schema_rows = spark.sql(f"""
        SELECT schema_name, tag_name, tag_value
        FROM system.information_schema.schema_tags
        WHERE catalog_name = '{catalog}' AND tag_name IN ({key_list})
        ORDER BY schema_name, tag_name
    """).collect()
    print(f"  Schema tags in UC: {len(schema_rows)}")
    for r in schema_rows:
        print(f"    {catalog}.{r.schema_name}: {r.tag_name} = '{r.tag_value}'")

    table_rows = spark.sql(f"""
        SELECT schema_name, table_name, tag_name, tag_value
        FROM system.information_schema.table_tags
        WHERE catalog_name = '{catalog}' AND tag_name IN ({key_list})
        ORDER BY schema_name, table_name, tag_name
    """).collect()
    print(f"  Table tags in UC:  {len(table_rows)}")
    for r in table_rows:
        print(f"    {catalog}.{r.schema_name}.{r.table_name}: {r.tag_name} = '{r.tag_value}'")

    if results['failed'] > 0 or schema_failures:
        raise Exception(
            f"TAG APPLICATION HAD FAILURES: "
            f"{results['failed']} table(s), {len(schema_failures)} schema(s)"
        )

summary = (
    f"success={results['success']}, failed={results['failed']}, "
    f"table_tags={total_tags}, schema_tags={schema_tags_applied}, dry_run={dry_run}"
)
print("\n" + "=" * 60)
print(f"SUMMARY: {summary}")

# NOTE: dbutils.notebook.exit() REPLACES this cell's entire output with the exit
# string, wiping the audit trail printed above and making the notebook look as
# though it was never run. Since this notebook exists to log an audit trail,
# only exit when a caller actually consumes the return value (dbutils.notebook.run
# or a job task) - controlled by the exit_on_complete widget.
if exit_on_complete:
    dbutils.notebook.exit(summary)

# COMMAND ----------

# DBTITLE 1,Apply COLUMN-level tags for ABAC column masking
# ============================================================================
# COLUMN-LEVEL TAGS
# ============================================================================
# ABAC column mask policies use MATCH COLUMNS has_tag('mnpi_column_masked')
# to identify which columns to mask. This requires the tag on individual COLUMNS,
# not just the table. mask_mnpi_value accepts VARIANT and returns VARIANT, so
# ALL column types can be tagged — STRING gets [MNPI RESTRICTED], others get NULL.
#
# Column selection comes from the raw securables YAML (not ResolvedTable, which
# doesn't carry mnpi_masked_columns / information_schema flags):
#   information_schema: true  → tag ALL columns in that table
#   mnpi_masked_columns: [..] → tag only those that EXIST (any type)
#   (neither)                 → tag all columns (table is mnpi_column_masked)
# ============================================================================
import yaml

print("COLUMN-LEVEL TAGS (for ABAC column masking)")
print("=" * 78)

# 1. Build a lookup from raw securables: (schema_id, table_id) -> config dict
volume_base = f"/Volumes/{catalog}/platform_admin/sdp_meta_files/conf/abac"
raw_table_configs = {}  # (schema_id, table_id) -> {info_schema, masked_cols}

for fname in ["bronze_securables.yml", "silver_securables.yml"]:
    fpath = f"{volume_base}/{fname}"
    try:
        with open(fpath) as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        print(f"  WARN: {fpath} not found — skipping")
        continue
    for sch in raw.get("schemas", []):
        sid = sch.get("schema_id")
        for tbl in sch.get("tables", []):
            tid = tbl.get("table_id")
            raw_table_configs[(sid, tid)] = {
                "information_schema": tbl.get("information_schema", False),
                "mnpi_masked_columns": tbl.get("mnpi_masked_columns", []),
            }

print(f"  Raw table configs loaded: {len(raw_table_configs)}")

# 2. For each manifest table with a mnpi_column_masked TABLE tag, resolve
#    which STRING columns to tag.
col_tags_applied = 0
col_tags_skipped = 0
col_warnings = []

for table in manifest.tables:
    if "mnpi_column_masked" not in (table.tags or {}):
        continue

    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    raw_cfg = raw_table_configs.get((table.schema, table.table_id), {})
    use_info_schema = raw_cfg.get("information_schema", False)
    declared_cols = raw_cfg.get("mnpi_masked_columns", []) or []

    # Query actual columns + types
    try:
        actual = spark.sql(f"""
            SELECT column_name, data_type
            FROM {table.catalog}.information_schema.columns
            WHERE table_schema = '{table.schema}'
              AND table_name = '{table.table_id}'
            ORDER BY ordinal_position
        """).collect()
    except Exception as e:
        col_warnings.append((fqn, f"cannot read columns: {e}"))
        continue

    actual_map = {r.column_name: r.data_type for r in actual}

    # Determine columns to tag — VARIANT UDF handles all types
    if use_info_schema:
        cols_to_tag = sorted(actual_map.keys())
        source = f"information_schema=true → all columns ({len(cols_to_tag)})"
    elif declared_cols:
        cols_to_tag = sorted(c for c in declared_cols if c in actual_map)
        # Warn about declared columns that don't exist
        for c in declared_cols:
            if c not in actual_map:
                col_warnings.append((fqn, f"declared col '{c}' does not exist"))
        source = f"mnpi_masked_columns ({len(declared_cols)} declared, {len(cols_to_tag)} exist)"
    else:
        # No column-level info in securables — tag all columns
        cols_to_tag = sorted(actual_map.keys())
        source = f"no column spec → all columns ({len(cols_to_tag)})"

    # Fallback: if declared mnpi_masked_columns resolved to 0 valid columns
    # (e.g. schema mismatch), fall back to all columns since the TABLE
    # is explicitly tagged mnpi_column_masked.
    if not cols_to_tag and declared_cols and actual_map:
        cols_to_tag = sorted(actual_map.keys())
        source += f" → FALLBACK all columns ({len(cols_to_tag)})"

    if not cols_to_tag:
        print(f"  SKIP    {fqn}: no columns to tag ({source})")
        col_tags_skipped += 1
        continue

    print(f"\n  ▶ {fqn} ({source})")

    for col in cols_to_tag:
        sql = f"ALTER TABLE {fqn} ALTER COLUMN `{col}` SET TAGS ('mnpi_column_masked' = '')"
        if dry_run:
            print(f"    DRY RUN {col}")
            col_tags_applied += 1
            continue
        try:
            spark.sql(sql)
            col_tags_applied += 1
            print(f"    OK      {col}")
        except Exception as e:
            col_warnings.append((fqn, f"col '{col}': {type(e).__name__}: {str(e)[:120]}"))
            print(f"    FAILED  {col}: {str(e)[:120]}")

# 3. Verify
if not dry_run:
    print(f"\nVERIFICATION (column_tags)")
    print("-" * 60)
    col_tag_rows = spark.sql(f"""
        SELECT schema_name, table_name, column_name, tag_value
        FROM {catalog}.information_schema.column_tags
        WHERE tag_name = 'mnpi_column_masked'
        ORDER BY schema_name, table_name, column_name
    """).collect()
    print(f"  Column tags in UC: {len(col_tag_rows)}")
    for r in col_tag_rows:
        print(f"    {catalog}.{r.schema_name}.{r.table_name}.{r.column_name}")

# 4. Summary
print(f"\n{'=' * 78}")
print(f"COLUMN TAG RESULTS")
print(f"  Applied: {col_tags_applied}{' (planned)' if dry_run else ''}")
print(f"  Skipped tables: {col_tags_skipped}")
if col_warnings:
    print(f"  Warnings: {len(col_warnings)}")
    for fqn, w in col_warnings:
        print(f"    {fqn}: {w}")