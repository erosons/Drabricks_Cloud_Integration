# SDP-META Framework + Bundle

Architecture, Use Case Patterns, and Diagrams

Generated: 2026-07-28  
Version: 1.0  
Package: `databricks-labs-sdp-meta 0.1.0`

## 1. Executive Summary

This document describes a unified SDP-META Framework + Bundle monorepo that combines the SDP-META framework source code with ingestion use case configurations into a single deployable unit using Databricks Asset Bundles (DAB). It supports two automation paths: framework code changes trigger automatic wheel rebuild and upload to a Unity Catalog volume, while use case configuration changes trigger new or updated ingestion pipelines and jobs.

## 2. Architecture Overview

### Design Principles

* Monorepo structure for framework code and configs, enabling atomic deployments
* DAB artifacts so `databricks bundle deploy` automatically builds the wheel
* UC Volume distribution so pipelines can `%pip install` from a volume and remain serverless-compatible
* Spec tables as the control plane, where onboarding JSON is written into bronze and silver spec tables that pipelines read dynamically
* Split bronze and silver pipelines for independent scaling

### Data Flow

1. Onboarding JSON defines source-to-target mappings.
2. The onboarding job writes mappings to bronze and silver `dataflowspec` tables.
3. Pipeline notebooks read those spec tables at runtime.
4. The SDP-META framework dynamically creates streaming tables.
5. Data quality expectations are applied from external JSON files.

## 3. Directory Structure

```text
sdp-meta-framework-bundle/
├── databricks.yml                         # DAB config with artifacts section
├── README.md
├── framework/                             # Framework source (wheel source)
│   ├── setup.py                           # Wheel build config
│   ├── src/databricks/labs/sdp_meta/      # Core framework modules
│   └── compat/                            # Backward compatibility shims
├── conf/                                  # Use case configurations
│   ├── onboarding_all_usecases.json       # Master onboarding (all 9 UCs)
│   ├── silver_transformations.json
│   ├── silver_transformations_fanout.json
│   └── dqe/                               # Data Quality Expectations
├── notebooks/                             # Pipeline runners and utilities
│   ├── init_sdp_meta_pipeline.py          # Standard runner
│   ├── init_sdp_meta_pipeline_snapshot.py
│   ├── build_wheel.py
│   └── upload_wheel_to_volume.py
├── resources/                             # DAB resource definitions
│   ├── variables.yml
│   ├── wheel_build_deploy_job.yml
│   ├── sdp_meta_onboarding_job.yml
│   └── sdp_meta_pipelines.yml
└── scripts/
    └── sync_framework.py
```

## 4. Framework Layer

Package: `databricks-labs-sdp-meta 0.1.0`  
Entry points: `run` for onboarding and `stage_conf` for volume staging.

### Key Modules

* `dataflow_pipeline.py` — core runtime with `invoke_dlt_pipeline(spark, layer)`
* `dataflow_spec.py` — spec table schema definitions
* `onboard_dataflowspec.py` — reads onboarding JSON and writes spec tables
* `pipeline_readers.py` — source readers for `cloudFiles`, `kafka`, `eventhub`, `snapshot`, and `delta`
* `pipeline_writers.py` — sink writers for Kafka and Delta
* `bundle.py` — DAB commands such as `bundle-prepare-wheel` and `bundle-init`
* `stage_conf.py` — copies `conf/` to a UC volume for serverless use

### Core Framework Files

#### `__about__.py`

This file is the single source of truth for the wheel version. It is read by `setup.py` during wheel build and stamped into pipelines at runtime so jobs can report which version they are running.

#### `dataflow_spec.py`

This file defines Python `@dataclass` objects that map one-to-one to columns in the Unity Catalog bronze and silver spec tables. Nested structures such as `CDCApplyChanges`, `AppendFlow`, `CDCApplyChangesFlowGroup`, and `DLTSink` are stored as JSON strings in spec-table columns.

#### `onboard_dataflowspec.py`

This module reads `onboarding_all_usecases.json`, validates identifiers and CDC-related settings, transforms each JSON object into rows matching the bronze and silver spec schemas, and writes those rows to Delta spec tables.

#### `dataflow_pipeline.py`

This runtime engine is invoked by `init_sdp_meta_pipeline.py`. It reads spec tables, filters by `data_flow_group`, and dynamically creates streaming tables using the Spark Declarative Pipelines API.

Key methods include:

* `invoke_dlt_pipeline(spark, layer)`
* `read_bronze()` and `read_silver()`
* `write_bronze()` and `write_silver()`
* `_get_row_filter()`
* CDC handling for `apply_changes`, `apply_changes_from_snapshot`, and `cdcApplyChangesFlows`

### Schema DDL Files (`conf/ddl/`)

The `conf/ddl/` directory contains Spark SQL DDL strings that define the source schema for each use case. These files are referenced in the onboarding JSON via `source_schema_path` and are staged to the UC Volume by the `stage_conf` task. At runtime, `PipelineReaders` reads the DDL and passes it as an explicit `StructType` to the source reader (AutoLoader `.schema()`, Kafka `from_json()`, etc.).

#### Files

| DDL File | Use Case | Source System |
| --- | --- | --- |
| `orders.ddl` | UC1 CloudFiles | CSV order files |
| `iot_events.ddl` | UC2 Kafka | IoT sensor stream |
| `eventhub_telemetry.ddl` | UC3 EventHub | Azure IoT telemetry |
| `customers_us.ddl` | UC5a Multi-CDC | US regional CRM |
| `customers_eu.ddl` | UC5b Multi-CDC | EU regional CRM |
| `customers_apac.ddl` | UC5c Multi-CDC | APAC regional CRM |
| `employees.ddl` | UC7 Row Filter | HR system |
| `payments.ddl` | UC8 Append Flows | Payment processor |

#### Convention: All Columns Are STRING (Industry Best Practice)

Every column in every DDL file is declared as `STRING`. No typed columns (TIMESTAMP, INT, DECIMAL, etc.) appear at the source-to-bronze boundary. Type casting is deferred entirely to the silver layer.

This is a deliberate architectural choice aligned with medallion architecture best practices:

**1. Lossless ingestion**

Raw data lands exactly as the source produced it. A malformed date like `"2024-13-45"`, a number with locale formatting like `"1.234,56"`, or an unexpected null representation like `"N/A"` all land safely in bronze as strings. With typed columns, these values would either be rejected (sent to `_rescued_data`) or silently coerced to null — both of which lose the original signal needed for debugging.

**2. Schema-on-read resilience**

Source systems change without notice. If an upstream OLTP switches timestamp format (ISO 8601 → epoch milliseconds) or adds decimal precision, bronze continues ingesting without interruption. The format change surfaces in silver where DQE expectations catch it gracefully — not as a pipeline-halting ingestion failure that pages the on-call engineer at 3 AM.

**3. Separation of concerns**

Bronze is responsible for one thing: capture everything the source sent. Silver is responsible for a different thing: validate, type-cast, and normalize. Mixing type enforcement into bronze conflates two distinct failure domains. When a data quality issue occurs, the root cause is immediately clear: if bronze has the data but silver rejected it, the issue is a format/validation problem. If bronze is missing the data, the issue is an ingestion/connectivity problem.

**4. Source fidelity for audit and compliance**

Regulatory workloads (GDPR, SOX, HIPAA) require demonstrating what the source system actually sent. A TIMESTAMP column that stored `2024-01-01 00:00:00` cannot prove whether the source originally sent `"2024-01-01"`, `"01/01/2024"`, `"1704067200000"`, or `"Jan 1, 2024"`. STRING columns preserve this provenance. Auditors can compare bronze against source extracts byte-for-byte.

**5. Replay and reprocessing**

When silver transformation logic changes (new date parsing rules, new decimal precision, corrected timezone handling), you can reprocess entirely from bronze without re-ingesting from the source. If bronze had already cast values and lost the original representation, reprocessing requires going back to the source system — which may no longer have the historical data, may have applied its own retention policies, or may charge for re-extraction.

#### Where Type Casting Happens

Proper types are enforced in the **silver layer** through `select_exp` in the onboarding JSON or in silver transformation files. Example:

```json
"select_exp": [
  "cust_id AS customer_id",
  "fname AS first_name",
  "lname AS last_name",
  "CAST(op_time AS TIMESTAMP) AS operation_date",
  "CAST(amount AS DECIMAL(10,2)) AS amount"
]
```

Data quality expectations in silver catch values that fail to cast, routing them to quarantine rather than losing them silently:

```json
"expect_or_quarantine": {
  "valid_timestamp": "operation_date IS NOT NULL",
  "valid_amount": "amount >= 0"
}
```

This two-phase approach (STRING bronze → typed silver with DQE) gives you both data completeness and data correctness without sacrificing either.

## 5. Use Cases

### UC1: CloudFiles (CSV) — Full Feature Demo

This use case demonstrates AutoLoader ingestion with metadata columns, schema DDL enforcement, liquid clustering, data quality expectations, and silver CDC with SCD Type 2.

Figure 1 and Figure 2 were extracted from the source document for UC1.

![Figure 1 UC1 data flow diagram](/images/uc1_dataflow.png)

*Figure 1: UC1 CloudFiles data flow diagram extracted from the source document.*
![Figure 1 UC2 data flow diagram](/images/uc1_dataflow.png)

![Figure 2 UC1 sequence diagram](/images/uc1_sequence.png)

### UC2: Kafka — Streaming with Dual Sinks
*Figure 2: UC2 Kafka data flow diagram extracted from the source document.*
![Figure 2 UC2 data flow diagram](/images/uc2_dataflow.png)
This use case ingests from Apache Kafka using SASL_SSL authentication and demonstrates bronze sinks that forward processed events to both Kafka and Delta.
Figure 2: UC2 Kafka sequence diagram extracted from the source document.*
![Figure 2 UC1 sequence diagram](/images/uc2_sequence.png)

### UC3: EventHub — Azure IoT with Append Flows

This use case ingests streaming data from Azure EventHub through the Kafka protocol adapter and demonstrates `bronze_append_flows` by merging a primary hub and an overflow hub into one table.

*Figure 3: UC3 EventHub data flow diagram extracted from the source document.*
![Figure 3 UC3 data flow diagram](/images/uc3_dataflow.png)

*Figure 6: UC3 EventHub sequence diagram extracted from the source document.*
![Figure 6 UC3 sequence diagram](/images/uc3_sequence.png)


### UC4: Snapshot CDC — Delta + CSV Versioned Snapshots

This use case covers two snapshot patterns: a Delta table snapshot source with SCD Type 2, and CSV file-based versioned snapshots with SCD Type 1. It uses `apply_changes_from_snapshot` at both layers.

*Figure 4: UC4 Snapshot CDC data flow diagram extracted from the source document.*
![Figure 4 UC4 data flow diagram](/images/uc4_dataflow.png)

*Figure 4: UC4 Snapshot CDC sequence diagram extracted from the source document.*
![Figure 4 UC4 sequence diagram](/images/uc4_sequence.png)


### UC5: Multi-Source CDC — Regional Merge

This use case ingests US, EU, and APAC regional sources with differing schemas into separate bronze tables, then merges them into a unified silver table through `silver_cdc_apply_changes_flows` with schema normalization.

*Figure 5: UC5 Multi-Source CDC data flow diagram extracted from the source document.*
![Figure 5 UC5 data flow diagram](/images/uc5_dataflow.png)

*Figure 5: UC5 Multi-Source CDC sequence diagram extracted from the source document.*
![Figure 5 UC5 sequence diagram](/images/uc5_sequence.png)


### UC6: Fanout — One Bronze to Multiple Silver

This use case ingests a single CSV source into one bronze table, then fans out into three silver tables using `where_clause` filters defined in `silver_transformations_fanout.json`.

*Figure 6: UC6 Fanout data flow diagram extracted from the source document.*
![Figure 6 UC5 data flow diagram](/images/uc6_dataflow.png)

*Figure 6: UC6 Fanout sequence diagram extracted from the source document.*
![Figure 12 UC6 sequence diagram](/images/uc6_sequence.png)


### UC7: Row Filter — Unity Catalog Row-Level Security

This use case demonstrates UC row-level security through a UDF-based filter applied to both bronze and silver layers so that only rows matching the current user's department access are visible.

![Figure 7 UC7 data flow diagram](/images/uc7_dataflow.png)

*Figure 7: UC7 Row Filter data flow diagram extracted from the source document.*

![Figure 7 UC7 sequence diagram](/images/uc7_sequence.png)

*Figure 7: UC7 Row Filter sequence diagram extracted from the source document.*


### UC8: Append Flows — Multiple Sources to One Table

This use case merges payment JSON files from three landing zones into a single bronze streaming table through `bronze_append_flows`.


![Figure 8 UC8 data flow diagram](/images/uc8_dataflow.png)

*Figure 15: UC8 Append Flows data flow diagram extracted from the source document.*

![Figure 8 UC8 sequence diagram](/images/uc8_sequence.png)

*Figure 16: UC8 Append Flows sequence diagram extracted from the source document.*

### UC9: Delta Source — Table-to-Table Replication

This use case reads from an upstream Delta table with Change Data Feed enabled and replicates those changes into a bronze table with liquid clustering. No silver layer is required.


![Figure 17 UC9 data flow diagram](/images/uc9_dataflow.png)

*Figure 17: UC9 Delta Source data flow diagram extracted from the source document.*

![Figure 18 UC9 sequence diagram](/images/uc9_sequence.png)

*Figure 18: UC9 Delta Source sequence diagram extracted from the source document.*


## 6. Pipeline Definitions

There are 15 pipelines. Each uses the same notebook with different Spark configuration values for layer, group, and wheel path. The standard pattern is: install the wheel, import `DataflowPipeline`, call `invoke_dlt_pipeline`, read the filtered spec-table group, and create streaming tables dynamically.

## 7. Resource Definitions (`resources/`)

The `resources/` directory contains all Declarative Automation Bundle (DAB) resource YAML files. These files declare jobs, pipelines, and variables that `databricks bundle deploy` materializes in the workspace. There are four files, each with a distinct responsibility.

### 7.1 `variables.yml` — Shared Configuration

This file defines all parameterized variables consumed by every other resource file via `${var.<name>}` interpolation. Variables provide a single place to change environment-specific values without editing job or pipeline definitions.

| Layer | Variables | Purpose |
| --- | --- | --- |
| Unity Catalog identity | `uc_catalog_name`, `sdp_meta_schema`, `bronze_schema`, `silver_schema` | Determines which catalog and schemas all tables, spec tables, and pipeline targets land in |
| Wheel distribution | `sdp_meta_dependency` | Full UC Volume path to the built `.whl` file; pipelines `%pip install` from this path |
| Volume storage | `uc_volume_path` | Base path for configs, test data, DDL files, and DQE JSON staged from `conf/` |
| Spec table naming | `bronze_dataflowspec_table`, `silver_dataflowspec_table` | Table names inside `sdp_meta_schema` where onboarding writes metadata rows |
| Environment | `env` | `dev` or `prod` — prefixed into job/pipeline display names for workspace separation |

Every variable has a `default` value so the bundle deploys out-of-the-box without requiring user overrides. Overrides can be supplied per-target in `databricks.yml` or via CLI `--var` flags.

### 7.2 `wheel_build_deploy_job.yml` — Framework CI Job

This job is triggered when framework source code changes. It rebuilds the wheel and makes it available to all pipelines.

**Job name:** `[${var.env}] SDP-META: Build Wheel & Deploy`

#### Task chain (sequential):

| # | Task key | Type | What it does |
| --- | --- | --- | --- |
| 1 | `build_wheel` | notebook_task | Runs `notebooks/build_wheel.py` which calls `pip wheel` against `framework/setup.py` to produce the `.whl` artifact |
| 2 | `upload_to_volume` | notebook_task | Runs `notebooks/upload_wheel_to_volume.py` which copies the built `.whl` from the ephemeral build directory to the UC Volume path in `${var.sdp_meta_dependency}` |
| 3 | `onboard_specs` | python_wheel_task | Installs the freshly uploaded wheel and invokes the `run` entry point to re-onboard all use cases, ensuring spec tables reference the latest version |

#### Environment layer:

All three tasks share the `wheel_build_env` serverless environment with dependencies: `databricks-sdk`, `PyYAML`, `setuptools`, and `wheel`. This keeps the build isolated from pipeline runtimes.

#### Key parameters passed to `onboard_specs`:

* `database` — fully qualified as `${var.uc_catalog_name}.${var.sdp_meta_schema}`
* `onboarding_file_path` — reads from the staged volume copy of the onboarding JSON
* `onboard_layer: bronze_silver` — onboards both layers in one pass
* `overwrite: "True"` — replaces existing spec rows so the build is idempotent

#### Schedule:

Paused by default (manual trigger). Uncomment the `quartz_cron_expression` for CI/CD automation.

#### Why `onboard_specs` is coupled to the wheel build (defensive design)

At first glance, re-onboarding spec tables after a wheel rebuild seems unnecessary — the onboarding JSON hasn't changed, so why rewrite the same rows? The coupling exists because the **onboarding logic itself lives inside the wheel**, and framework changes can silently alter what gets written to the spec tables:

1. **Schema evolution** — A new wheel version may add columns to the dataflowspec schema (e.g., `rowFilter`, `cdcApplyChangesFlows`, `appendFlowsSchemas`). Spec rows written by the old wheel won't have these columns populated. Pipelines running the new wheel code would read `None` for the missing fields, potentially causing silent data gaps or runtime errors.

2. **Validation rule changes** — The onboarding parser (`onboard.py`) validates and normalizes JSON before writing. A bug fix or stricter validation in the new wheel may produce different output rows from the same input JSON — correcting silently malformed data that the old version let through.

3. **Default value changes** — When optional fields gain new defaults (e.g., `overwrite` semantics, CDC sequence handling), re-onboarding ensures existing spec rows reflect the new defaults rather than carrying stale nulls.

4. **Idempotency guarantee** — Because the task uses `overwrite: "True"`, re-onboarding is a no-op when nothing meaningful changed. The cost is a few seconds of compute; the benefit is eliminating an entire class of "wheel/spec version mismatch" debugging sessions.

**Trade-off:** Most wheel changes (reader logic, writer logic, pipeline_readers.py) do NOT affect the spec schema. In those cases, `onboard_specs` runs unnecessarily. This is accepted as an intentional trade-off — a small runtime cost vs. guaranteed consistency. The alternative (manual coordination between wheel deploys and spec refreshes) introduces human error and is the more dangerous failure mode in production.

**When to run onboarding separately (use `sdp_meta_onboarding_job` instead):**

* Adding new use cases to the onboarding JSON without changing framework code
* Changing source paths, connection strings, or DQE rules in `conf/`
* Re-onboarding after correcting a typo in the JSON config

In these cases the wheel hasn't changed, so rebuilding it would be wasteful.

### 7.3 `sdp_meta_onboarding_job.yml` — Use Case Onboarding Job

This job loads configuration JSON into the spec tables that drive all pipelines. Run it when adding new use cases or changing source configurations.

**Job name:** `[${var.env}] SDP-META: Onboard All Use Cases`

#### Task chain (sequential):

| # | Task key | Type | What it does |
| --- | --- | --- | --- |
| 1 | `stage_conf` | python_wheel_task | Invokes the `stage_conf` entry point which copies the entire `conf/` directory from the workspace to the UC Volume at `${var.uc_volume_path}/conf`. This is required because serverless pipelines cannot read workspace files directly — they need volume-hosted paths |
| 2 | `onboard_bronze_silver` | python_wheel_task | Invokes the `run` entry point which reads `onboarding_all_usecases.json` from the volume, validates each flow object, and writes rows into `bronze_dataflowspec_table` and `silver_dataflowspec_table` |

#### Environment layer:

Both tasks use `onboarding_env` with `databricks-sdk` and `PyYAML`. The wheel itself is loaded via `libraries: [whl: ${var.sdp_meta_dependency}]` — it is NOT pip-installed from PyPI but loaded directly from the UC Volume.

#### Key parameters passed to `onboard_bronze_silver`:

* `database` — target schema for spec tables
* `onboarding_file_path` — the volume-hosted JSON (staged in task 1)
* `onboard_layer: bronze_silver` — writes both bronze and silver specs
* `overwrite: "True"` — full replace each run (not append)
* `env: ${var.env}` — resolves `{env}` tokens inside the onboarding JSON (e.g., file paths that differ between dev and prod)

#### Difference from `wheel_build_deploy_job`:

The onboarding job does NOT rebuild the wheel — it assumes the wheel already exists on the volume. Use this job for config-only changes. Use the wheel build job for framework code changes (it includes onboarding as its final step).

### 7.4 `sdp_meta_pipelines.yml` — All Pipelines + Orchestration Job

This is the largest resource file. It declares all 15 Lakeflow Spark Declarative Pipelines (one or two per use case) and a single orchestration job that runs them all.

#### Pipeline declaration pattern

Every pipeline follows an identical structure:

```yaml
pipeline_<layer>_<use_case>:
  name: "[${var.env}] SDP-META <Layer>: <Use Case>"
  catalog: ${var.uc_catalog_name}
  target: ${var.<layer>_schema}
  channel: PREVIEW
  libraries:
    - notebook:
        path: ${workspace.file_path}/notebooks/init_sdp_meta_pipeline.py
  configuration:
    layer: <bronze|silver>
    <layer>.dataflowspecTable: <fully qualified spec table>
    <layer>.group: <data_flow_group value>
    bundle.sourcePath: ${workspace.file_path}/notebooks
    sdp_meta_whl: ${var.sdp_meta_dependency}
```

#### Configuration keys explained:

| Key | Purpose |
| --- | --- |
| `layer` | Tells `invoke_dlt_pipeline` whether to read bronze or silver spec rows |
| `<layer>.dataflowspecTable` | Fully qualified spec table to query at runtime |
| `<layer>.group` | Filters spec table rows to only the flows belonging to this pipeline |
| `bundle.sourcePath` | Base path for resolving relative notebook references |
| `sdp_meta_whl` | Volume path for the `%pip install` command in the runner notebook |

#### Pipeline inventory (15 pipelines):

| Use Case | Bronze Pipeline | Silver Pipeline | Runner Notebook |
| --- | --- | --- | --- |
| UC1: CloudFiles | `pipeline_bronze_cloudfiles` | `pipeline_silver_cloudfiles` | `init_sdp_meta_pipeline.py` |
| UC2: Kafka | `pipeline_bronze_kafka` | — | `init_sdp_meta_pipeline.py` |
| UC3: EventHub | `pipeline_bronze_eventhub` | — | `init_sdp_meta_pipeline.py` |
| UC4: Snapshot | `pipeline_bronze_snapshot` | `pipeline_silver_snapshot` | `init_sdp_meta_pipeline_snapshot.py` |
| UC5: Multi-CDC | `pipeline_bronze_multi_cdc` | `pipeline_silver_multi_cdc` | `init_sdp_meta_pipeline.py` |
| UC6: Fanout | `pipeline_bronze_fanout` | `pipeline_silver_fanout` | `init_sdp_meta_pipeline.py` |
| UC7: Row Filter | `pipeline_bronze_row_filter` | `pipeline_silver_row_filter` | `init_sdp_meta_pipeline.py` |
| UC8: Append Flows | `pipeline_bronze_append_flows` | — | `init_sdp_meta_pipeline.py` |
| UC9: Delta Source | `pipeline_bronze_delta` | — | `init_sdp_meta_pipeline.py` |

UC4 (Snapshot) uses a different runner notebook (`init_sdp_meta_pipeline_snapshot.py`) because snapshot sources require the `next_snapshot_and_version` callback which is not needed by streaming sources.

#### Orchestration job: `run_all_pipelines`

**Job name:** `[${var.env}] SDP-META: Run All Pipelines`

This job executes all 15 pipelines with correct dependency ordering:

* **Bronze tier (9 tasks, run in parallel):** `bronze_cloudfiles`, `bronze_kafka`, `bronze_eventhub`, `bronze_snapshot`, `bronze_multi_cdc`, `bronze_fanout`, `bronze_row_filter`, `bronze_append_flows`, `bronze_delta`
* **Silver tier (5 tasks, each depends on its bronze counterpart):** `silver_cloudfiles` → waits on `bronze_cloudfiles`; `silver_snapshot` → waits on `bronze_snapshot`; `silver_multi_cdc` → waits on `bronze_multi_cdc`; `silver_fanout` → waits on `bronze_fanout`; `silver_row_filter` → waits on `bronze_row_filter`

Each task uses `pipeline_task` with a `pipeline_id` reference like `${resources.pipelines.pipeline_bronze_cloudfiles.id}`, which DAB resolves at deploy time to the actual pipeline ID.

#### Why bronze runs before silver:

Silver pipelines read from bronze streaming tables via Delta CDC or direct streaming reads. If silver starts before bronze has materialized data, the silver pipeline either fails (table not found) or produces no output (empty source). The `depends_on` graph ensures bronze completes first.

### 7.5 How the files relate

```text
variables.yml
    │
    ├──► wheel_build_deploy_job.yml    (uses vars for paths, schemas, env)
    │         └── task: onboard_specs  (same logic as onboarding job)
    │
    ├──► sdp_meta_onboarding_job.yml   (uses vars for paths, schemas, env)
    │         └── writes to spec tables
    │
    └──► sdp_meta_pipelines.yml        (uses vars for catalog, schemas, wheel)
              ├── 15 pipeline declarations (read spec tables at runtime)
              └── run_all_pipelines job (orchestrates the 15 pipelines)
```

Changing a variable in `variables.yml` propagates to all three resource files on the next `databricks bundle deploy`.

## 8. Deployment Workflows

### Initial Setup

1. Run `scripts/sync_framework.py` optionally.
2. Deploy with `databricks bundle deploy --target dev`.
3. Run the setup notebook to provision schemas, volumes, and test data.
4. Run `databricks bundle run sdp_meta_onboarding`.
5. Run `databricks bundle run run_all_pipelines`.

### Framework Update

1. Edit `framework/src/databricks/labs/sdp_meta/`.
2. Run `databricks bundle deploy` to auto-build the wheel.
3. Pipelines pick up the new wheel on the next refresh.

### New Use Case

1. Add a new entry to `conf/onboarding_all_usecases.json`.
2. Add the pipeline to `resources/sdp_meta_pipelines.yml`.
3. Optionally add DQE and silver transformations.
4. Run `databricks bundle deploy`.
5. Run `databricks bundle run sdp_meta_onboarding`.

### System-Level Deployment Sequence

Figure 19 was extracted from the source document and shows the end-to-end deployment and execution flow from bundle deployment to pipeline execution.

![Figure 19 system deployment sequence](sdp_meta_docx_inspect/image11.png)

*Figure 19: System-level end-to-end deployment sequence extracted from the source document.*

## 9. Extending the Framework

### Adding a New Source Format

1. Edit `framework/src/databricks/labs/sdp_meta/pipeline_readers.py`.
2. Add a reader class or method for the new format.
3. Register it in `SUPPORTED_SOURCE_FORMATS` in `identifiers.py`.
4. Rebuild the wheel with `databricks bundle deploy`.
5. Add a use case using `source_format: "new_format"`.

### Adding New Bronze or Silver Features

1. Define the new field in onboarding JSON.
2. Update `dataflow_spec.py`.
3. Update `dataflow_pipeline.py`.
4. Rebuild the wheel and re-onboard.

### Custom Pipeline Notebooks

1. Create `notebooks/init_sdp_meta_pipeline_custom.py`.
2. Import or extend `DataflowPipeline`, or write custom DLT logic.
3. Reference the notebook in `resources/sdp_meta_pipelines.yml`.
4. Continue using `%pip install $sdp_meta_whl` for framework utilities.

### Adding New Onboarding JSON Fields

New onboarding JSON fields are ignored until they are explicitly handled. To make a new field functional:

1. Add parsing logic to `onboard_dataflowspec.py`.
2. Add a schema column to `dataflow_spec.py`.
3. Add runtime behavior to `dataflow_pipeline.py`.
4. Increment the version in `__about__.py`.

## 10. Variables Reference

| Variable | Default | Purpose |
|---|---|---|
| `uc_catalog_name` | `users` | UC catalog |
| `sdp_meta_schema` | `samson_eromonsei_sdp_meta_specs` | Spec tables schema |
| `bronze_schema` | `samson_eromonsei_sdp_meta_bronze` | Bronze schema |
| `silver_schema` | `samson_eromonsei_sdp_meta_silver` | Silver schema |
| `sdp_meta_dependency` | `/Volumes/.../wheels/...whl` | Wheel on volume |
| `uc_volume_path` | `/Volumes/.../sdp_meta_files` | Volume for configs |
| `env` | `dev` | Environment |

## 11. Onboarding JSON Schema Reference

Key fields per flow object:

| Field | Description |
|---|---|
| `data_flow_id` | Unique numeric ID |
| `data_flow_group` | Groups flows into pipelines |
| `source_format` | `cloudFiles`, `kafka`, `eventhub`, `snapshot`, or `delta` |
| `source_details` | Source paths, topics, and connection information |
| `bronze_reader_options` | Format-specific reader configuration |
| `bronze_data_quality_expectations_json_dev` | Path to DQE file |
| `bronze_cluster_by` / `bronze_cluster_by_auto` | Liquid clustering settings |
| `bronze_append_flows` | Additional append sources |
| `bronze_sinks` | Output sinks such as Kafka or Delta |
| `bronze_row_filter` | Unity Catalog row-level security |
| `silver_cdc_apply_changes` | CDC keys, `sequence_by`, and `scd_type` |
| `silver_cdc_apply_changes_flows` | Multi-source CDC merge |
| `silver_apply_changes_from_snapshot` | Snapshot CDC |
| `silver_transformation_json_dev` | Path to silver transformations |
| `silver_row_filter` | Silver row security |

## 12. Troubleshooting

* Wheel not found: ensure the `wheel_build_and_deploy` job ran and verify the volume path.
* Pipeline fails on `%pip install`: verify `sdp_meta_whl` points to a valid volume path.
* Onboarding fails: check JSON syntax, `{token}` placeholders, and that the spec schema exists.
* DQE file not found: stage `conf/` to the volume using the onboarding job's `stage_conf` task.
* Spec table empty: verify `data_flow_group` matches the pipeline's `bronze.group` value.
