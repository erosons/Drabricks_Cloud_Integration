# SDP-META Framework + Bundle (Unified Monorepo)

This is a **unified monorepo** that combines the SDP-META framework source code
with the ingestion use case configurations. It provides a single deployment
unit where:

- **Framework changes** → automatically rebuild the wheel and upload to UC Volume
- **Use case changes** → create/update ingestion pipelines and jobs

## Directory Structure

```
sdp-meta-framework-bundle/
├── databricks.yml                          # DAB config with artifacts section
├── README.md                               # This file
├── framework/                              # SDP-META framework source (wheel source)
│   ├── setup.py                            # Wheel build configuration
│   ├── MANIFEST.in                         # Non-Python file inclusion
│   ├── README.md                           # Package README
│   ├── FRAMEWORK_README.md                 # Framework maintenance docs
│   ├── src/databricks/labs/sdp_meta/       # Core framework code
│   └── compat/                             # Backward compatibility shims
├── conf/                                   # Use case configurations
│   ├── onboarding_all_usecases.json        # Master onboarding config (all 9 UCs)
│   ├── silver_transformations.json         # Silver layer select_exp + where_clause
│   ├── silver_transformations_fanout.json   # Fanout-specific transformations
│   └── dqe/                                # Data Quality Expectations
│       ├── uc1_orders/
│       ├── uc2_kafka/
│       ├── uc3_eventhub/
│       └── uc8_append/
├── notebooks/                              # Pipeline and utility notebooks
│   ├── init_sdp_meta_pipeline.py           # Standard pipeline runner
│   ├── init_sdp_meta_pipeline_snapshot.py  # Snapshot pipeline runner (UC4)
│   ├── build_wheel.py                      # Wheel build task notebook
│   └── upload_wheel_to_volume.py           # Wheel upload task notebook
├── resources/                              # DAB resource definitions
│   ├── variables.yml                       # All bundle variables
│   ├── wheel_build_deploy_job.yml          # Framework change → wheel rebuild
│   ├── sdp_meta_onboarding_job.yml         # Use case change → re-onboard
│   └── sdp_meta_pipelines.yml              # All 15 pipelines + execution job
└── scripts/
    └── sync_framework.py                   # Sync framework from standalone repo
```

## How It Works

### Two Trigger Paths

```
┌─────────────────────────────────────────────────────────────────────┐
│                    databricks bundle deploy                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  framework/ changed?                  conf/ changed?                │
│       │                                    │                        │
│       ▼                                    ▼                        │
│  [Artifacts: whl]                  [Onboarding Job]                 │
│  Auto-build wheel ─────┐           Refresh spec tables              │
│                        │                   │                        │
│                        ▼                   ▼                        │
│              UC Volume: /Volumes/...      bronze_dataflowspec_table │
│                        │                  silver_dataflowspec_table │
│                        │                   │                        │
│                        └───────┬───────────┘                        │
│                                │                                    │
│                                ▼                                    │
│                    [15 Pipelines Read Specs]                        │
│                    Use new wheel + new configs                      │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Workflow A: Framework Code Change

1. Edit code in `framework/src/databricks/labs/sdp_meta/`
2. Run: `databricks bundle deploy`
   - DAB `artifacts` section auto-builds the wheel from `framework/`
3. OR run the `wheel_build_and_deploy` job manually:
   - Builds wheel → uploads to UC Volume → re-onboards specs
4. Pipelines pick up new wheel on next refresh

### Workflow B: New Ingestion Use Case

1. Add new entry to `conf/onboarding_all_usecases.json`
2. Add pipeline definition to `resources/sdp_meta_pipelines.yml`
3. Run: `databricks bundle deploy`
4. Run the `sdp_meta_onboarding` job to populate spec tables
5. Run the new pipeline

## Initial Setup

### 1. Sync Framework Source

Run the sync script to copy framework code from `local-meta-sdp`:

```bash
# Option A: Run the sync notebook in Databricks
# Navigate to scripts/sync_framework.py and run it

# Option B: Local copy (if working with git)
cp -r ../local-meta-sdp/src framework/src
cp -r ../local-meta-sdp/compat framework/compat
cp ../local-meta-sdp/MANIFEST.in framework/
cp ../local-meta-sdp/README.md framework/
```

### 2. Deploy the Bundle

```bash
cd sdp-meta-framework-bundle
databricks bundle deploy --target dev
```

### 3. Provision Infrastructure

Run the setup notebook (create schemas, volumes, test data):
- Use the `setup_all_usecases` notebook from the companion test bundle, OR
- Create equivalent infrastructure manually

### 4. Onboard Use Cases

```bash
databricks bundle run sdp_meta_onboarding --target dev
```

### 5. Run Pipelines

```bash
# Run all pipelines
databricks bundle run run_all_pipelines --target dev

# Or run individual pipelines
databricks bundle run pipeline_bronze_cloudfiles --target dev
```

## 9 Use Cases Covered

| UC | Group | Source | Bronze Features | Silver Features |
|---|---|---|---|---|
| 1 | `uc1_cloudfiles` | CSV via AutoLoader | DQE, quarantine, liquid clustering, metadata | CDC SCD Type 2 |
| 2 | `uc2_kafka` | Kafka stream | DQE, quarantine, Kafka+Delta sinks | — |
| 3 | `uc3_eventhub` | Azure EventHub | DQE, quarantine, append_flows | — |
| 4 | `uc4_snapshot` | Delta + CSV snapshots | apply_changes_from_snapshot | SCD Type 1 + 2 |
| 5 | `uc5_multi_cdc` | JSON (US/EU/APAC) | Multi-region ingestion | Multi-source CDC merge |
| 6 | `uc6_fanout` | CSV vehicles | Single table | 1→N fanout (where_clause) |
| 7 | `uc7_row_filter` | CSV employees | Row-level security (UDF) | Row filter propagation |
| 8 | `uc8_append_flows` | JSON payments | Multiple landing zones → 1 table | — |
| 9 | `uc9_delta` | Delta table (CDF) | Table-to-table replication | — |

## Variables Reference

| Variable | Default | Purpose |
|---|---|---|
| `uc_catalog_name` | `users` | Unity Catalog catalog |
| `sdp_meta_schema` | `samson_eromonsei_sdp_meta_specs` | Schema for spec tables |
| `bronze_schema` | `samson_eromonsei_sdp_meta_bronze` | Bronze layer schema |
| `silver_schema` | `samson_eromonsei_sdp_meta_silver` | Silver layer schema |
| `sdp_meta_dependency` | `/Volumes/.../wheels/...whl` | Wheel path on UC Volume |
| `uc_volume_path` | `/Volumes/.../sdp_meta_files` | Volume for configs + data |
| `env` | `dev` | Environment identifier |

## Key Design Decisions

1. **Monorepo over multi-repo**: Framework + configs in one place for atomic deployments
2. **DAB artifacts for wheel build**: `databricks bundle deploy` auto-builds the wheel
3. **UC Volume for wheel distribution**: Pipelines `%pip install` from volume (serverless compatible)
4. **Spec tables as control plane**: Onboarding JSON → spec tables → pipelines read dynamically
5. **Split pipelines**: Separate bronze/silver for independent scaling and debugging

## ABAC Governance Module

The `abac/` directory implements Attribute-Based Access Control (ABAC) on top of
Databricks Unity Catalog policies. Notebooks 00–07 manage the full lifecycle:
tag application, RBAC grants, UDF deployment, policy creation, enforcement
validation, drift detection, and MNPI expiration.

### Known Limitations

#### 1. Group Membership Cache Delay (~5 minutes)

**Risk: Data Proliferation Window**

Databricks caches account group membership for both the ABAC policy engine
(`TO`/`EXCEPT` clause evaluation) and the `is_account_group_member()` UDF.
The cache TTL is approximately **5 minutes** on serverless SQL warehouses.

This means that when a user is **removed** from the `{domain}_{layer}_mnpi_approved`
(EXCEPT) group, there is a window of up to 5 minutes during which:

* The policy engine still treats them as exempt (mask not applied)
* The UDF still returns `true` for their old group membership
* The user can query and **export unmasked MNPI data** during this window
* Any data copied, downloaded, or piped to an external system during the
  window is **irrecoverable** — the mask cannot retroactively redact it

The same delay applies in reverse (adding a user to the group takes ~5 minutes
to take effect), but that direction is lower risk (delayed access grant, not
delayed access revocation).

**Mitigations (ordered by effectiveness):**

| # | Mitigation | Effectiveness | Disruption | Implementation |
|---|---|---|---|---|
| 1 | **Revoke RBAC grants BEFORE removing from EXCEPT group** | Strongest | Low — affects only the target user | Revoke `SELECT` on the schema/catalog first. RBAC revocations are enforced at the catalog authorization layer, not the query-time mask layer, and take effect faster. Without `SELECT`, the user cannot query at all regardless of the mask cache state. Once the ~5 min mask cache expires, re-grant `SELECT` to the user's base group (e.g. `data_readers`) so they see masked data again. |
| 2 | **Restart the SQL warehouse** | Immediate (flushes all caches) | High — disrupts all concurrent users | Only practical for dedicated per-team warehouses. Not viable for shared production warehouses. |
| 3 | **Dedicated warehouse per sensitivity tier** | Structural | Medium — operational overhead | Assign MNPI-approved users to a dedicated warehouse that can be restarted without affecting the broader user base. |
| 4 | **Audit logging + post-hoc detection** | Detective (not preventive) | None | Query `system.access.audit` and `system.query.history` to identify any queries executed by the revoked user during the cache window. Flag data exports (COPY INTO, downloads, JDBC reads) for review. |
| 5 | **Dual approval for EXCEPT removal** | Process control | None (human process) | Require that EXCEPT group removal goes through a change ticket with a 5-minute "cool-down" step where the user's warehouse session is terminated first. |

> **Recommended procedure for removing MNPI access:**
>
> 1. `REVOKE SELECT ON SCHEMA {catalog}.{schema} FROM \`user_or_group\``
> 2. Remove user from `{domain}_{layer}_mnpi_approved` group
> 3. Wait 5 minutes (or restart the user's warehouse)
> 4. `GRANT SELECT ON SCHEMA {catalog}.{schema} TO \`{domain}_{layer}_data_readers\``
>    (re-grants to the base group so the user sees masked data)
>
> This ensures **zero-window exposure**: the user loses query access immediately
> (step 1), and by the time it is restored (step 4) the mask cache has expired.

**Platform request:** This cache TTL is a Databricks platform behavior and
cannot be configured per-workspace or per-warehouse. If sub-minute revocation
is a regulatory requirement, file a feature request for configurable
`is_account_group_member()` cache TTL or real-time group membership eviction.

#### 2. VARIANT Column Type for Masked Users

The `mask_mnpi_value` UDF accepts `VARIANT` and returns `VARIANT` to support
masking across all column types with a single function. This means that
**unauthorized users** (in `TO` but not in `EXCEPT`) see masked columns with
`VARIANT` type instead of the native type (e.g. `DOUBLE`, `TIMESTAMP`).

* `SUM(amount)` fails for masked users — requires `SUM(amount::DOUBLE)`
* BI tools with strict type expectations may show errors for masked columns
* **Authorized users (in EXCEPT) are unaffected** — the mask is bypassed
  entirely and columns retain their native types

Since masked users see `[MNPI RESTRICTED]` (STRING) or `NULL` (all other types),
aggregations on masked data are meaningless regardless of type. This is an
acceptable trade-off for universal single-UDF coverage.

#### 3. `is_account_group_member()` Is Not Recursive for Nested Groups

If your identity provider (Okta, Entra ID) uses nested group structures,
`is_account_group_member()` checks **direct membership only**. A user in
`GRP_PARENT` that contains `finance_bronze_mnpi_approved` as a child group
will NOT pass the membership check. Ensure MNPI-approved users are **direct
members** of the policy's EXCEPT group.

#### 4. Column Mask Policies Fail at CREATE POLICY Time

Both `mnpi_column_masking` COLUMN MASK policies currently fail with
`INVALID_PARAMETER_VALUE` when created via `CREATE POLICY` in notebook 04.
The row filter policies deploy successfully. The column mask policies were
previously deployed interactively and remain active in Unity Catalog —
enforcement is verified working. Root cause investigation is pending.

#### 5. Non-Existent Principals Cause Policy Failure

Databricks `CREATE POLICY` validates that all principals in `TO` and `EXCEPT`
clauses exist as account-level groups or users. If a group referenced in
`policies.yml` templates (e.g. `GRP_OKTA_{productname}_{company}_{environment}_{application}_{layer}_mnpi_approved`)
does not exist in the Databricks account, the entire policy creation fails.
Ensure all groups are provisioned in the account before running notebook 04.
