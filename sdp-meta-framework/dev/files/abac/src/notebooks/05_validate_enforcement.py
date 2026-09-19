# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# DBTITLE 1,Step 05: Validate ABAC Enforcement
"""
Step 05: Validate ABAC Enforcement

Validation is driven by the ACTUAL deployed policy state (SHOW EFFECTIVE
POLICIES), not by template resolution. The previous version of this notebook
could not work, for three reasons:
  1. It used ABACConfigLoader, which is dead in this bundle (hardcodes
     policies.yaml; the file on disk is policies.yml).
  2. It derived "columns that should be masked" from
     TemplateResolver.resolve_column_tags, but spec_table_reader builds the
     manifest with templates={}, so that always resolves ZERO columns.
  3. Its mask regexes expected ***@domain.com / (***) ***-XXXX / ***-**-XXXX,
     but the deployed UDF mask_mnpi_value emits the literal '[MNPI RESTRICTED]'.

Three stages:
  1. Effective policy inventory per sampled table (authoritative)
  2. Principal-scope analysis - is the CURRENT user actually subject to each
     policy (in TO, and not in EXCEPT)? If not, masked/cleartext observations
     prove NOTHING about enforcement.
  3. Data-level probe - look for the mask sentinel and row-filter effects
"""
import sys
import os
import re
import random
import yaml
import importlib

dbutils.widgets.text("project_root", "", "Project Root")
dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("bronze_spec_table", "employee_dataflowspec_bronze", "Bronze Spec Table")
dbutils.widgets.text("silver_spec_table", "employee_dataflowspec_silver", "Silver Spec Table")
dbutils.widgets.text("policies_path", "", "Policies Path (defaults to {project_root}/configs/policies.yml)")
dbutils.widgets.text("mapping_table", "abac_dataflowspec_mapping", "ABAC Mapping Table Name")
dbutils.widgets.text("sample_size", "10", "Tables to sample")
dbutils.widgets.text("exit_on_complete", "false", "Call notebook.exit() at the end (true for job runs)")

project_root = dbutils.widgets.get("project_root") or "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac"
catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
bronze_spec_table = dbutils.widgets.get("bronze_spec_table")
silver_spec_table = dbutils.widgets.get("silver_spec_table")
mapping_table = dbutils.widgets.get("mapping_table")
policies_path = dbutils.widgets.get("policies_path") or f"{project_root}/configs/policies.yml"
sample_size = int(dbutils.widgets.get("sample_size"))
exit_on_complete = dbutils.widgets.get("exit_on_complete").lower() == "true"

sys.path.insert(0, f"{project_root}/src")

importlib.invalidate_caches()
for _mod in ["config_loader", "spec_table_reader", "policy_inheritance", "mnpi_expiration"]:
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])

from spec_table_reader import EnhancedSpecTableABACLoader
from policy_inheritance import apply_inheritance_to_manifest

# The sentinel emitted by mask_mnpi_value in policies.yml udf_registry.
MASK_SENTINEL = "[MNPI RESTRICTED]"

current_user = spark.sql("SELECT current_user()").collect()[0][0]

print(f"Project root: {project_root}")
print(f"Policies:     {policies_path}")
print(f"Catalog:      {catalog} | Spec schema: {sdp_meta_schema}")
print(f"Sample size:  {sample_size} tables")
print(f"Current user: {current_user}")
print(f"Mask sentinel: {MASK_SENTINEL!r}")

# COMMAND ----------

# DBTITLE 1,Load manifest and select sample
# Load governance manifest from spec tables (ABACConfigLoader is dead here).
loader = EnhancedSpecTableABACLoader(
    spark, catalog, sdp_meta_schema,
    bronze_spec_table, silver_spec_table,
    policies_path, mapping_table,
)
manifest = loader.load()
manifest = apply_inheritance_to_manifest(manifest)

# Policy definitions keyed by policy_id, for TO/EXCEPT principal analysis later.
policy_defs = {}
for _kind, _ptype in (("row_filters", "row_filter"), ("column_masks", "column_mask")):
    for p in manifest.policies.get("policies", {}).get(_kind, []):
        policy_defs[p["policy_id"]] = {**p, "policy_type": _ptype}

# schema_id -> domain/layer, needed to resolve {domain}_{layer} in principals.
schema_ctx = {
    s["schema_id"]: {"domain": s.get("domain"), "layer": s.get("layer")}
    for s in manifest.schemas
}

# Candidate tables. Schema-scoped policies land in inherited_policy_bindings
# after apply_inheritance_to_manifest, so BOTH lists must be checked.
tables_with_policies = [
    t for t in manifest.tables
    if t.policy_bindings or t.inherited_policy_bindings
]

if len(tables_with_policies) <= sample_size:
    sample_tables = tables_with_policies
else:
    sample_tables = random.sample(tables_with_policies, sample_size)

print(f"Tables in manifest:      {len(manifest.tables)}")
print(f"Tables with a binding:   {len(tables_with_policies)}")
print(f"Sampled for validation:  {len(sample_tables)}")
print(f"Policy definitions:      {list(policy_defs.keys())}")
print()
for t in sample_tables:
    fqn = f"{t.catalog}.{t.schema}.{t.table_id}"
    pol = sorted(set(t.policy_bindings) | set(t.inherited_policy_bindings))
    ctx = schema_ctx.get(t.schema, {})
    print(f"  {fqn}  [{ctx.get('domain')}/{ctx.get('layer')}]")
    print(f"      bindings: {', '.join(pol) or '(none)'}")
    print(f"      tags:     {t.tags or {}}")

# COMMAND ----------

# DBTITLE 1,Stage 1+2: effective policies and principal scope
# STAGE 1: what does UC actually enforce on each sampled table?
# STAGE 2: is the CURRENT user in scope for each of those policies?
#
# Stage 2 is the part the old notebook was missing entirely. An ABAC policy only
# applies to principals listed in TO (minus those in EXCEPT). If the running user
# is in neither, queries come back unfiltered/cleartext and that says nothing at
# all about whether enforcement works.

def resolve_tpl(s, domain, layer):
    """Resolve {domain}/{layer} placeholders in a principal template."""
    if not isinstance(s, str):
        return s
    return s.replace("{domain}", domain or "").replace("{layer}", layer or "")

_group_cache = {}

def is_member(group):
    """Cached is_account_group_member. Returns None if the check errors."""
    if group not in _group_cache:
        try:
            _group_cache[group] = spark.sql(
                f"SELECT is_account_group_member('{group}')"
            ).collect()[0][0]
        except Exception:
            _group_cache[group] = None
    return _group_cache[group]

print("STAGE 1+2 - EFFECTIVE POLICIES AND PRINCIPAL SCOPE")
print("=" * 78)

effective = {}   # fqn -> list of effective-policy row dicts
in_scope = {}    # (fqn, policy_name) -> True / False / None(unknown)

for table in sample_tables:
    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    print(f"\n\u25b6 {fqn}")

    try:
        rows = spark.sql(f"SHOW EFFECTIVE POLICIES ON TABLE {fqn}").collect()
    except Exception as e:
        print(f"    \u2717 SHOW EFFECTIVE POLICIES failed: {str(e)[:130]}")
        effective[fqn] = []
        continue

    effective[fqn] = [r.asDict() for r in rows]
    if not rows:
        print("    (no effective policies)")
        continue

    ctx = schema_ctx.get(table.schema, {})
    for r in rows:
        d = r.asDict()
        pname = d.get("Policy Name")
        ptype = d.get("Policy Type")
        origin = f"{d.get('on_securable_type')} {d.get('on_securable_fullname')}"
        print(f"    - {pname} ({ptype}) inherited from {origin}")

        pdef = policy_defs.get(pname)
        if not pdef:
            in_scope[(fqn, pname)] = None
            print("        scope: UNKNOWN (policy not declared in policies.yml)")
            continue

        to_groups = [resolve_tpl(p, ctx.get("domain"), ctx.get("layer"))
                     for p in pdef.get("principals", {}).get("to", [])]
        ex_groups = [resolve_tpl(p, ctx.get("domain"), ctx.get("layer"))
                     for p in pdef.get("principals", {}).get("except", [])]

        to_hits = {g: is_member(g) for g in to_groups}
        ex_hits = {g: is_member(g) for g in ex_groups}
        in_to = any(v is True for v in to_hits.values())
        in_ex = any(v is True for v in ex_hits.values())
        subject = in_to and not in_ex
        in_scope[(fqn, pname)] = subject

        print(f"        TO     {to_hits}")
        print(f"        EXCEPT {ex_hits}")
        print(f"        -> current user subject to this policy: {subject}")

# COMMAND ----------

# DBTITLE 1,Stage 3: data-level probe
# STAGE 3: probe actual data for the mask sentinel and row-filter effects.
# Only STRING columns are probed: mask_mnpi_value is STRING->STRING, so it can
# never be bound to a numeric/date column anyway.
print("\n\nSTAGE 3 - DATA-LEVEL PROBE")
print("=" * 78)

probe = []          # (fqn, column, verdict, sample_value)
tables_probed = 0
tables_failed = 0
row_counts = {}

for table in sample_tables:
    fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    print(f"\n\u25b6 {fqn}")

    try:
        cols = spark.sql(f"""
            SELECT column_name, data_type
            FROM {table.catalog}.information_schema.columns
            WHERE table_schema = '{table.schema}'
              AND table_name = '{table.table_id}'
            ORDER BY ordinal_position
        """).collect()
    except Exception as e:
        print(f"    \u2717 cannot read columns: {str(e)[:110]}")
        tables_failed += 1
        continue

    string_cols = [c.column_name for c in cols
                   if str(c.data_type).upper() in ("STRING", "VARCHAR")]
    probe_cols = string_cols[:5]

    if not probe_cols:
        print(f"    (no STRING columns among {len(cols)}; "
              f"mask_mnpi_value is STRING-only so nothing here can be masked)")
        continue

    sel = ", ".join(f"`{c}`" for c in probe_cols)
    try:
        rows = spark.sql(f"SELECT {sel} FROM {fqn} LIMIT 5").collect()
        visible = spark.sql(f"SELECT count(*) AS n FROM {fqn}").collect()[0]["n"]
    except Exception as e:
        print(f"    \u2717 query failed: {str(e)[:160]}")
        tables_failed += 1
        continue

    tables_probed += 1
    row_counts[fqn] = visible
    print(f"    visible rows: {visible}  |  probing: {', '.join(probe_cols)}")

    if not rows:
        print("    \u26a0 0 rows visible - empty table OR a fully-restrictive row filter")
        probe.append((fqn, "*", "NO_ROWS", ""))
        continue

    for c in probe_cols:
        vals = [r[c] for r in rows if r[c] is not None]
        if not vals:
            print(f"      {c}: (all NULL in sample)")
            continue
        masked = [v for v in vals if MASK_SENTINEL in str(v)]
        if masked:
            probe.append((fqn, c, "MASKED", str(vals[0])[:40]))
            print(f"    \u2713 {c}: MASKED  e.g. {str(vals[0])[:40]!r}")
        else:
            probe.append((fqn, c, "CLEARTEXT", str(vals[0])[:40]))
            print(f"      {c}: cleartext  e.g. {str(vals[0])[:40]!r}")

# COMMAND ----------

# DBTITLE 1,Enforcement validation summary
# Summary + an HONEST verdict that distinguishes "enforcement works" from
# "we were never in a position to observe enforcement".
masked_n = len([p for p in probe if p[2] == "MASKED"])
clear_n = len([p for p in probe if p[2] == "CLEARTEXT"])
norows_n = len([p for p in probe if p[2] == "NO_ROWS"])

all_pol = [d for ds in effective.values() for d in ds]
row_filters = [d for d in all_pol if str(d.get("Policy Type")).upper() == "ROW_FILTER"]
col_masks = [d for d in all_pol if str(d.get("Policy Type")).upper() == "COLUMN_MASK"]
subject_true = [k for k, v in in_scope.items() if v is True]
subject_false = [k for k, v in in_scope.items() if v is False]

print(f"\n{'=' * 78}")
print("ENFORCEMENT VALIDATION RESULTS")
print(f"{'=' * 78}")
print(f"  Current user:              {current_user}")
print(f"  Tables sampled:           {len(sample_tables)}")
print(f"  Tables probed:            {tables_probed}")
print(f"  Tables failed:            {tables_failed}")
print(f"  Effective ROW_FILTER:     {len(row_filters)}")
print(f"  Effective COLUMN_MASK:    {len(col_masks)}")
print(f"  Policies user IS subject: {len(subject_true)}")
print(f"  Policies user NOT subject:{len(subject_false)}")
print(f"  Column checks MASKED:     {masked_n}")
print(f"  Column checks cleartext:  {clear_n}")
print(f"  Tables with 0 rows:       {norows_n}")
print(f"{'=' * 78}")

print("\nVERDICT")
if not all_pol:
    print("  \u2717 NO effective policies on any sampled table.")
    print("    Nothing is being enforced. Run 04_create_abac_policies with")
    print("    dry_run=false first.")
elif not subject_true:
    print("  \u26a0 INCONCLUSIVE - the current user is NOT a TO principal on any")
    print("    effective policy, so ABAC does not apply to these queries.")
    print("    The cleartext values above are EXPECTED and prove NOTHING about")
    print("    whether enforcement works.")
    print("    To genuinely validate, run as a member of a *_data_readers group")
    print("    that is NOT also in the matching *_mnpi_approved group.")
elif masked_n and not clear_n:
    print("  \u2713 MASKING ACTIVE on every probed column.")
elif masked_n and clear_n:
    print("  \u2713 PARTIAL masking - some columns masked, some cleartext.")
    print("    Expected when only tag-matched columns are masked.")
else:
    print("  \u2717 The user IS subject to a policy but NO masking was observed.")
    print("    This is a real finding - investigate the policy binding.")

if not col_masks:
    print("\n  \u26a0 NO effective COLUMN_MASK policies found. Root cause:")
    print("    'mnpi_column_masked' is applied as a TABLE tag, but a COLUMN MASK")
    print("    policy resolves its target column via MATCH COLUMNS, which matches")
    print("    COLUMN-level tags. This catalog currently has 0 column tags, so the")
    print("    MATCH COLUMNS clause matches nothing and the policy never binds.")
    print("    Fix: tag the specific columns to mask, then change the policy to")
    print("    MATCH COLUMNS has_column_tag('<column_tag>').")

summary = (
    f"probed={tables_probed}, row_filters={len(row_filters)}, "
    f"col_masks={len(col_masks)}, subject={len(subject_true)}, "
    f"masked={masked_n}, cleartext={clear_n}, failed={tables_failed}"
)
print(f"\nSUMMARY: {summary}")

if exit_on_complete:
    dbutils.notebook.exit(summary)

# COMMAND ----------

