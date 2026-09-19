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
1. Load manifest from the SDP-META spec tables -> UC Volume SecurableRegistry
2. Route privileges to the correct securable level (CATALOG/SCHEMA/TABLE)
3. VALIDATE every declared grant against the canonical persona privilege sets
   in policies.yml `grants`, then build a deduplicated grant plan
4. If grant_rbac_permissions=true, execute grants in parallel batches;
   otherwise report that the permission assignment is valid and apply nothing
5. Verify with SHOW GRANTS

VALIDATION CONTRACT: policies.yml `grants` defines the canonical privilege set
per persona (data_reader, data_editor). The registry declares per-schema groups
(`hr_data_readers`, `employee_silver_data_editors`, ...). A declared group is
mapped to its persona by name suffix, and its privileges must equal the subset
of the persona's canonical set that is legal at the declared securable level
(USE CATALOG is not grantable ON SCHEMA, so it is compared only at catalog
level). A mismatch raises when fail_on_mismatch=true.

ABACConfigLoader is NOT used: it hardcodes 'policies.yaml' (file is
'policies.yml') and expects a configs/securables/ tree that does not exist in
this bundle, so .load() raises FileNotFoundError.
"""
import sys
import os
import yaml
import importlib
from concurrent.futures import ThreadPoolExecutor, as_completed

dbutils.widgets.text("config_path", "", "Config Directory")
dbutils.widgets.text("project_root", "", "Project Root")
dbutils.widgets.text("use_cached_manifest", "false", "Use Cached Manifest (true/false)")
dbutils.widgets.text("catalog", "general_use", "UC Catalog")
dbutils.widgets.text("sdp_meta_schema", "sdp_meta", "SDP Meta Schema")
dbutils.widgets.text("bronze_spec_table", "employee_dataflowspec_bronze", "Bronze Spec Table")
dbutils.widgets.text("silver_spec_table", "employee_dataflowspec_silver", "Silver Spec Table")
dbutils.widgets.text("policies_path", "", "Policies Path (defaults to {project_root}/configs/policies.yml)")
dbutils.widgets.text("mapping_table", "abac_dataflowspec_mapping", "ABAC Mapping Table Name")
dbutils.widgets.text("grant_rbac_permissions", "true", "Apply the GRANT statements (true) or validate only (false)")
dbutils.widgets.text("fail_on_mismatch", "true", "Raise if a declared grant does not match its persona (true/false)")
dbutils.widgets.text("exit_on_complete", "false", "Call notebook.exit() at the end (true for job runs)")

config_path = dbutils.widgets.get("config_path") or "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac/configs"
project_root = dbutils.widgets.get("project_root") or "/Workspace/deployment/.bundle/sdp-meta-framework/dev/files/abac"
use_cached_manifest = dbutils.widgets.get("use_cached_manifest").lower() == "true"
catalog = dbutils.widgets.get("catalog")
sdp_meta_schema = dbutils.widgets.get("sdp_meta_schema")
bronze_spec_table = dbutils.widgets.get("bronze_spec_table")
silver_spec_table = dbutils.widgets.get("silver_spec_table")
mapping_table = dbutils.widgets.get("mapping_table")
# Validate always; only APPLY when explicitly enabled.
grant_rbac_permissions = dbutils.widgets.get("grant_rbac_permissions").lower() == "true"
fail_on_mismatch = dbutils.widgets.get("fail_on_mismatch").lower() == "true"
# dbutils.notebook.exit() discards everything a cell printed, so it is opt-in.
exit_on_complete = dbutils.widgets.get("exit_on_complete").lower() == "true"

policies_path = dbutils.widgets.get("policies_path") or f"{project_root}/configs/policies.yml"

sys.path.insert(0, f"{project_root}/src")

# Modules under {project_root}/src stay cached in the REPL after being edited on
# disk; reload in dependency order (config_loader first) so ResolvedTable and
# GovernanceManifest come from the current source.
importlib.invalidate_caches()
for _mod in ["config_loader", "spec_table_reader", "policy_inheritance"]:
    if _mod in sys.modules:
        importlib.reload(sys.modules[_mod])

from spec_table_reader import EnhancedSpecTableABACLoader
from policy_inheritance import apply_inheritance_to_manifest

print(f"Project root:  {project_root}")
print(f"Policies:      {policies_path}")
print(f"Catalog:       {catalog} | Spec schema: {sdp_meta_schema}")
print(f"Apply grants:  {grant_rbac_permissions}")
print(f"Fail on mismatch: {fail_on_mismatch}")
print(f"Exit on complete: {exit_on_complete}")

# COMMAND ----------

# DBTITLE 1,Restage v2 securables to UC Volume
# Exclude when deploying through Bundle - Restage the v2 securables from bundle source to the UC Volume so 
# EnhancedSpecTableABACLoader picks up the persona-keyed grants + domain/layer.
from databricks.sdk import WorkspaceClient
import pathlib

w = WorkspaceClient()

bundle_conf = "/deployment/.bundle/sdp-meta-framework/dev/files/conf/abac"
volume_conf = "/Volumes/general_use/platform_admin/sdp_meta_files/conf/abac"

for fname in ["bronze_securables.yml", "silver_securables.yml"]:
    src_path = f"{bundle_conf}/{fname}"
    dst_path = f"{volume_conf}/{fname}"
    # Read from workspace (bypasses FUSE cache)
    content = w.workspace.download(src_path).read()
    # Write to UC Volume via FUSE (Volumes are writable this way)
    pathlib.Path(dst_path).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(dst_path).write_bytes(content)
    print(f"  Staged {fname} ({len(content):,} bytes)")

# Verify the v2 shape landed
import yaml
for fname in ["bronze_securables.yml", "silver_securables.yml"]:
    doc = yaml.safe_load(pathlib.Path(f"{volume_conf}/{fname}").read_text())
    print(f"\n  {fname} (version {doc['metadata'].get('version')})")
    for sch in doc.get("schemas", []):
        print(f"    schema {sch['schema_id']}: domain={sch.get('domain')}, "
              f"layer={sch.get('layer')}, grants={sch.get('grants')!r}")

print("\n\u2713 Volume copy restaged with v2 shape")

# COMMAND ----------

# DBTITLE 1,Load manifest and define privilege routing
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
    loader = EnhancedSpecTableABACLoader(
        spark, catalog, sdp_meta_schema,
        bronze_spec_table, silver_spec_table,
        policies_path, mapping_table,
    )
    manifest = loader.load()
    # Returns the manifest itself, not a (manifest, stats) tuple.
    manifest = apply_inheritance_to_manifest(manifest)

print(f"Catalogs: {len(manifest.catalogs)}")
print(f"Schemas:  {len(manifest.schemas)}")
print(f"Tables:   {manifest.stats['total_tables']}")

# Canonical persona -> privilege set, from policies.yml `grants`.
# This is the contract every declared grant in the registry is measured against.
CANONICAL_GRANTS = {}
for _entry in (manifest.policies.get("grants") or []):
    _g = _entry.get("group")
    if not _g:
        raise ValueError(f"policies.yml grants entry missing 'group': {_entry}")
    CANONICAL_GRANTS[_g] = {p.strip().upper() for p in (_entry.get("privileges") or [])}

if not CANONICAL_GRANTS:
    raise ValueError(
        f"No 'grants' section found in {policies_path}. 03b validates declared "
        f"registry grants against it, so it cannot run without one."
    )

print(f"\nCanonical personas from policies.yml: {len(CANONICAL_GRANTS)}")
for _p, _privs in CANONICAL_GRANTS.items():
    print(f"  {_p}: {sorted(_privs)}")

# All valid privileges at each securable level (from UC privilege reference)
# Scope: CATALOG, SCHEMA, TABLE only

CATALOG_PRIVILEGES = {
    "USE CATALOG", "USE SCHEMA",
    "APPLY TAG", "BROWSE", "EXECUTE", "READ FEATURE", "READ SECRET",
    "READ VOLUME", "REFERENCE SECRET", "SELECT", "USE CONNECTION",
    "MODIFY", "REFRESH", "WRITE SECRET", "WRITE VOLUME",
    "CREATE CONNECTION", "CREATE FEATURE", "CREATE FLOW", "CREATE FUNCTION",
    "CREATE MATERIALIZED VIEW", "CREATE MEMORY STORE", "CREATE MODEL",
    "CREATE MODEL VERSION", "CREATE SCHEMA", "CREATE SECRET",
    "CREATE SERVICE", "CREATE TABLE", "CREATE VOLUME",
    "ALL PRIVILEGES", "EXTERNAL USE SCHEMA", "MANAGE",
}

SCHEMA_PRIVILEGES = {
    "USE SCHEMA",
    "APPLY TAG", "EXECUTE", "READ FEATURE", "READ VOLUME",
    "SELECT", "USE CONNECTION",
    "MODIFY", "REFRESH", "WRITE VOLUME",
    "CREATE CONNECTION", "CREATE FEATURE", "CREATE FLOW", "CREATE FUNCTION",
    "CREATE MATERIALIZED VIEW", "CREATE MEMORY STORE", "CREATE MODEL",
    "CREATE MODEL VERSION", "CREATE SERVICE", "CREATE TABLE", "CREATE VOLUME",
    "ALL PRIVILEGES", "MANAGE",
}

TABLE_PRIVILEGES = {
    "APPLY TAG", "MODIFY", "SELECT", "ALL PRIVILEGES", "MANAGE",
}

# When a privilege is NOT valid at the declared level, route it here
FLEXIBLE_PRIVILEGES = {
    "USE CATALOG": "catalog",
    "USE SCHEMA": "schema",
    "BROWSE": "catalog",
}

LEVEL_PRIVILEGE_MAP = {
    "catalog": CATALOG_PRIVILEGES,
    "schema": SCHEMA_PRIVILEGES,
    "table": TABLE_PRIVILEGES,
}

def route_privilege(priv, securable_level):
    """Determine the correct ON clause for a privilege.
    
    1. If privilege is valid at the declared level -> keep it there
    2. If NOT valid -> check FLEXIBLE_PRIVILEGES for routing
    3. Otherwise -> skip (return None to filter it out)
    """
    priv_upper = priv.strip().upper()
    valid_at_level = LEVEL_PRIVILEGE_MAP.get(securable_level, set())

    if priv_upper in valid_at_level:
        return securable_level
    elif priv_upper in FLEXIBLE_PRIVILEGES:
        return FLEXIBLE_PRIVILEGES[priv_upper]
    else:
        # Not valid at this level and not flexible — try to find correct level
        if priv_upper in SCHEMA_PRIVILEGES:
            return "schema"
        elif priv_upper in CATALOG_PRIVILEGES:
            return "catalog"
        else:
            return None  # Unknown privilege, skip

def resolve_persona(group_name=None, persona_name=None):
    """Resolve a canonical persona from either the v2 key or a legacy group name.

    v2 schema grants are persona-keyed:
        grants:
          data_reader: hr_bronze_data_readers
          data_editor: hr_bronze_data_editors

    In that shape the KEY is already the canonical persona, so prefer it.
    The suffix-based fallback remains for legacy explicit grant lists and any
    bespoke entries that still need best-effort persona inference.
    """
    if persona_name:
        p = persona_name.strip()
        if p in CANONICAL_GRANTS:
            return p
        return None

    g = (group_name or "").strip().lower()
    for persona in CANONICAL_GRANTS:
        p = persona.strip().lower()
        if g in (p, f"{p}s") or g.endswith(f"_{p}") or g.endswith(f"_{p}s"):
            return persona
    return None


def expected_privileges_at_level(persona, level):
    """The part of a persona's canonical set that is legal at `level`.

    Used only for legacy/external explicit privilege lists. In the v2
    persona-keyed shape, the schema declaration names the persona and 03b
    routes the FULL canonical set to the correct UC levels when building the
    grant plan.
    """
    valid_here = LEVEL_PRIVILEGE_MAP.get(level, set())
    return {p for p in CANONICAL_GRANTS[persona] if p in valid_here}


print("\u2713 Privilege routing logic defined")
print(f"  Catalog: {len(CATALOG_PRIVILEGES)} | Schema: {len(SCHEMA_PRIVILEGES)} | Table: {len(TABLE_PRIVILEGES)}")

# COMMAND ----------

# DBTITLE 1,Validate declared grants and build grant plan
# ============================================================================
# STAGE 1: Collect every grant declared in the securables registry
# ============================================================================
# manifest.catalogs contains the same catalog once per registry file (bronze and
# silver each declare general_use), so declarations are deduplicated on
# (level, fqn, group, privileges, persona, mode).
declarations = []
seen_decls = set()


def add_declaration(level, fqn, group, privileges, source, persona=None,
                    declaration_mode="explicit", context=None):
    privs = sorted({p.strip().upper() for p in (privileges or []) if p and p.strip()})
    key = (level, fqn, group, tuple(privs), persona, declaration_mode)
    if key in seen_decls:
        return
    seen_decls.add(key)
    declarations.append({
        "level": level,
        "fqn": fqn,
        "group": group,
        "privileges": privs,
        "source": source,
        "persona": persona,
        "declaration_mode": declaration_mode,
        "context": context or {},
    })


for cat in manifest.catalogs:
    cid = cat["catalog_id"]
    for grant in cat.get("grants") or []:
        add_declaration(
            "catalog", cid, grant["group"], grant.get("privileges") or [],
            f"CATALOG {cid}",
            persona=resolve_persona(group_name=grant.get("group")),
            declaration_mode="explicit",
        )

for sch in manifest.schemas:
    schema_fqn = f"{sch['catalog']}.{sch['schema_id']}"
    schema_domain = sch.get("domain")
    schema_layer = sch.get("layer")
    schema_grants = sch.get("grants") or []

    # v2 shape:
    #   grants:
    #     data_reader: hr_bronze_data_readers
    #     data_editor: hr_bronze_data_editors
    # The key IS the canonical persona, so synthesize the full persona privilege
    # set here and let Stage 3 route USE CATALOG / USE SCHEMA / SELECT / MODIFY /
    # CREATE TABLE to the correct UC levels.
    if isinstance(schema_grants, dict):
        missing_ctx = [k for k in ("domain", "layer") if not sch.get(k)]
        if missing_ctx:
            raise ValueError(
                f"{schema_fqn} uses v2 persona-keyed grants but is missing "
                f"required field(s): {missing_ctx}"
            )

        for declared_persona, group in schema_grants.items():
            persona = resolve_persona(group_name=group, persona_name=declared_persona)
            add_declaration(
                "schema", schema_fqn, group,
                CANONICAL_GRANTS.get(persona, set()),
                f"SCHEMA {schema_fqn} [{schema_domain}/{schema_layer}]",
                persona=persona,
                declaration_mode="persona_keyed",
                context={
                    "declared_persona": declared_persona,
                    "domain": schema_domain,
                    "layer": schema_layer,
                },
            )

    # legacy shape: explicit list of {group, privileges}
    elif isinstance(schema_grants, list):
        for grant in schema_grants:
            add_declaration(
                "schema", schema_fqn, grant["group"], grant.get("privileges") or [],
                f"SCHEMA {schema_fqn}",
                persona=resolve_persona(group_name=grant.get("group")),
                declaration_mode="explicit",
                context={"domain": schema_domain, "layer": schema_layer},
            )
    elif schema_grants:
        raise TypeError(
            f"Unsupported grants shape for {schema_fqn}: expected dict or list, "
            f"found {type(schema_grants).__name__}"
        )

# Table-level `grants` in the registry is a DICT, not a list:
#     grants:
#       exceptions:
#         - group: finance_bronze_mnpi_approved
# Those are ABAC policy EXCEPTION groups consumed by 04_create_abac_policies -
# they carry no `privileges` and are NOT RBAC grants. Collected here for
# reporting only. If a true table-level RBAC privilege list is ever added, keep
# it under `privileges_by_group` so it is unambiguous.
policy_exceptions = []
for table in manifest.tables:
    table_fqn = f"{table.catalog}.{table.schema}.{table.table_id}"
    tgrants = getattr(table, "grants", None) or {}
    if isinstance(tgrants, dict):
        for exc in tgrants.get("exceptions") or []:
            policy_exceptions.append((table_fqn, exc.get("group")))
        for grant in tgrants.get("privileges_by_group") or []:
            add_declaration(
                "table", table_fqn, grant["group"], grant.get("privileges") or [],
                f"TABLE {table_fqn}",
                persona=resolve_persona(group_name=grant.get("group")),
                declaration_mode="explicit",
            )
    elif isinstance(tgrants, list):
        for grant in tgrants:
            if grant.get("privileges"):
                add_declaration(
                    "table", table_fqn,
                    grant.get("group", grant.get("role", "")),
                    grant["privileges"], f"TABLE {table_fqn}",
                    persona=resolve_persona(group_name=grant.get("group", grant.get("role", ""))),
                    declaration_mode="explicit",
                )

print(f"Declared grants collected: {len(declarations)}")
print(f"Table policy exceptions (consumed by notebook 04, not RBAC): {len(policy_exceptions)}")
for _fqn, _grp in policy_exceptions:
    print(f"    {_fqn} EXCEPT {_grp}")

# ============================================================================
# STAGE 2: Validate each declaration against its canonical persona
# ============================================================================
matched, mismatched, unmapped, invalid_persona_keys = [], [], [], []

for d in declarations:
    persona = d.get("persona") or resolve_persona(group_name=d["group"])
    d["persona"] = persona
    declared = set(d["privileges"])

    if d["declaration_mode"] == "persona_keyed":
        if persona is None:
            d["invalid_reason"] = (
                "persona key is not defined in policies.yml grants: "
                f"{d['context'].get('declared_persona')}"
            )
            invalid_persona_keys.append(d)
            continue

        d["expected"] = set(CANONICAL_GRANTS[persona])
        d["missing"] = []
        d["extra"] = []
        matched.append(d)
        continue

    if persona is None:
        unmapped.append(d)
        continue

    expected = expected_privileges_at_level(persona, d["level"])
    d["expected"] = expected
    d["missing"] = sorted(expected - declared)
    d["extra"] = sorted(declared - expected)
    (matched if not d["missing"] and not d["extra"] else mismatched).append(d)

print("\n" + "=" * 78)
print("GRANT VALIDATION against policies.yml personas")
print("=" * 78)

for d in matched:
    mode = d["declaration_mode"]
    suffix = ""
    if mode == "persona_keyed":
        suffix = f" [v2 {d['context'].get('domain')}/{d['context'].get('layer')}]"
    print(f"  VALID     {d['level'].upper():7} {d['fqn']:30} {d['group']:34} [{d['persona']}]" + suffix)
for d in invalid_persona_keys:
    print(f"  INVALID   {d['level'].upper():7} {d['fqn']:30} {d['group']:34} "
          f"[{d['context'].get('declared_persona')}]")
    print(f"            {d['invalid_reason']}")
for d in unmapped:
    print(f"  UNMAPPED  {d['level'].upper():7} {d['fqn']:30} {d['group']:34} "
          f"{sorted(set(d['privileges']))}")
    print(f"            no canonical persona in policies.yml - not validated")
for d in mismatched:
    print(f"  MISMATCH  {d['level'].upper():7} {d['fqn']:30} {d['group']:34} [{d['persona']}]")
    print(f"              declared: {sorted(set(d['privileges']))}")
    print(f"              expected: {sorted(d['expected'])}")
    if d["missing"]:
        print(f"              MISSING : {d['missing']}")
    if d["extra"]:
        print(f"              EXTRA   : {d['extra']}")

# A persona's canonical set spans securable levels (USE CATALOG at catalog,
# USE SCHEMA/SELECT/MODIFY/CREATE TABLE at schema), so check each validated
# persona-mapped group has every canonical privilege represented SOMEWHERE after
# interpretation of the declaration shape.
by_group = {}
for d in declarations:
    if not d.get("persona"):
        continue
    effective_privs = (
        set(CANONICAL_GRANTS[d["persona"]])
        if d["declaration_mode"] == "persona_keyed"
        else set(d["privileges"])
    )
    by_group.setdefault((d["group"], d["persona"]), set()).update(effective_privs)

coverage_gaps = []
for (_group, _persona), _declared_all in sorted(by_group.items()):
    _missing_all = sorted(CANONICAL_GRANTS[_persona] - _declared_all)
    if _missing_all:
        coverage_gaps.append((_group, _persona, _missing_all))

if coverage_gaps:
    print("\n  COVERAGE GAPS - persona privilege never declared at ANY level:")
    for _group, _persona, _missing_all in coverage_gaps:
        print(f"    {_group:34} [{_persona}] never granted: {_missing_all}")
    print("    Effect: the group cannot reach the objects it has SELECT on until")
    print("    the missing privilege is declared at a level that permits it.")

print("\n" + "=" * 78)
print(f"  Valid:              {len(matched)}")
print(f"  Invalid persona:    {len(invalid_persona_keys)}")
print(f"  Mismatched:         {len(mismatched)}")
print(f"  Unmapped:           {len(unmapped)}")
print(f"  Coverage gaps:      {len(coverage_gaps)}")
print("=" * 78)

if (invalid_persona_keys or mismatched) and fail_on_mismatch:
    problems = []
    problems.extend(
        f"invalid persona-keyed grant {d['level']} {d['fqn']} {d['group']} "
        f"declared_persona={d['context'].get('declared_persona')}"
        for d in invalid_persona_keys
    )
    problems.extend(
        f"{d['level']} {d['fqn']} {d['group']} missing={d['missing']} extra={d['extra']}"
        for d in mismatched
    )
    raise ValueError(
        f"GRANT VALIDATION FAILED: {len(invalid_persona_keys) + len(mismatched)} "
        f"declaration(s) are invalid -> " + "; ".join(problems)
    )

# ============================================================================
# STAGE 3: Build a deduplicated grant plan from the validated declarations
# ============================================================================
grant_plan = []
seen_grants = set()

def add_grant(priv_list, on_type, on_fqn, group, source_desc):
    """Add routed GRANT statements to the plan, deduplicating."""
    routed = {}
    for p in sorted({p.strip().upper() for p in (priv_list or []) if p and p.strip()}):
        level = route_privilege(p, on_type.lower())
        if level is not None:
            routed.setdefault(level, []).append(p)

    for level, privs in routed.items():
        priv_str = ", ".join(sorted(set(privs)))
        if level == "catalog":
            catalog = on_fqn.split(".")[0]
            sql = f"GRANT {priv_str} ON CATALOG `{catalog}` TO `{group}`"
        elif level == "schema":
            parts = on_fqn.split(".")
            schema_fqn = ".".join(parts[:2]) if len(parts) >= 2 else on_fqn
            sql = f"GRANT {priv_str} ON SCHEMA `{'`.`'.join(schema_fqn.split('.'))}` TO `{group}`"
        else:
            sql = f"GRANT {priv_str} ON TABLE `{'`.`'.join(on_fqn.split('.'))}` TO `{group}`"

        if sql not in seen_grants:
            seen_grants.add(sql)
            grant_plan.append((sql, source_desc))

for d in declarations:
    if d["declaration_mode"] == "persona_keyed" and not d.get("persona"):
        continue
    effective_privileges = (
        CANONICAL_GRANTS[d["persona"]]
        if d.get("persona") and d["declaration_mode"] == "persona_keyed"
        else d["privileges"]
    )
    add_grant(
        effective_privileges,
        d["level"].upper(),
        d["fqn"],
        d["group"],
        f"{d['level'].upper()} {d['fqn']} -> {d['group']}"
    )

print(f"\nGrant plan: {len(grant_plan)} unique statements")
print("=" * 60)
for sql, desc in grant_plan[:20]:
    print(f"  {desc}")
if len(grant_plan) > 20:
    print(f"  ... and {len(grant_plan) - 20} more")

# COMMAND ----------

# DBTITLE 1,Execute grants in parallel (gated)
# Execute all GRANT statements in parallel
max_workers = 20

granted = []
failed = []

# Validation already passed by the time this cell runs (cell 3 raises otherwise).
# Applying is a separate, explicit decision.
if not grant_rbac_permissions:
    print("=" * 78)
    print("VALIDATION ONLY - grant_rbac_permissions=false")
    print("=" * 78)
    print(f"  Permission assignment is VALID: {len(matched)} declared grant(s) match")
    print(f"  their persona definitions in policies.yml.")
    print(f"  {len(grant_plan)} GRANT statement(s) would be executed:")
    for _sql, _desc in grant_plan:
        print(f"    {_sql}")
    print("\n  Set grant_rbac_permissions=true to apply them.")

print(f"\nApplying {len(grant_plan) if grant_rbac_permissions else 0} RBAC grants "
      f"(max {max_workers} parallel)...")
print("=" * 60)

def execute_grant(item):
    sql, desc = item
    try:
        spark.sql(sql)
        return ("success", sql, desc, None)
    except Exception as e:
        return ("failed", sql, desc, str(e)[:200])

if grant_rbac_permissions:
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
else:
    print("  (skipped - validate-only mode)")

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
print(f"  Declarations:   {len(declarations)}")
print(f"  Valid:          {len(matched)}")
print(f"  Mismatched:     {len(mismatched)}")
print(f"  Unmapped:       {len(unmapped)}")
print(f"  Coverage gaps:  {len(coverage_gaps)}")
print(f"  Total planned:  {len(grant_plan)}")
print(f"  Executed:       {len(granted)}")
print(f"  Failed:         {len(failed)}")
print(f"  Tables covered: {manifest.stats['total_tables']}")
print(f"  Apply mode:     grant_rbac_permissions={grant_rbac_permissions}")

if failed:
    print(f"\n\u26a0 Failures (may require elevated privileges):")
    for desc, err in failed[:10]:
        print(f"    - {desc}: {err[:80]}")

if failed:
    raise Exception(f"RBAC GRANT HAD {len(failed)} FAILURE(S)")

summary = (
    f"valid={len(matched)}, mismatched={len(mismatched)}, unmapped={len(unmapped)}, "
    f"planned={len(grant_plan)}, granted={len(granted)}, failed={len(failed)}, "
    f"applied={grant_rbac_permissions}"
)
print("\n" + "=" * 78)
print(f"SUMMARY: {summary}")

# NOTE: dbutils.notebook.exit() REPLACES this cell's entire output with the exit
# string, wiping the verification trail above. Gated so interactive runs stay
# auditable and job runs can still return a value.
if exit_on_complete:
    dbutils.notebook.exit(summary)