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
