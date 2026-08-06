# Change Request: UC10 — Watermark-Based Incremental Ingestion from Federated OLTP

## Status: PROPOSED

## Problem Statement

Large federated OLTP tables (SQL Server, PostgreSQL, Oracle) at terabyte scale cannot be ingested using the existing UC4 snapshot pattern. Full-table reads on every refresh are impractical because:

* Network transfer cost is prohibitive (terabytes over JDBC per refresh)
* Query load on the source OLTP degrades production workloads
* 99.9% of rows are unchanged — only the delta since last read matters

## Proposed Pattern: Watermark-Based Incremental Read

### Concept

Use a monotonically increasing column (timestamp or sequence ID) as a high-watermark to track the last-processed position. Each pipeline refresh queries only rows where the watermark column exceeds the previously recorded value.

```
Source: federated_catalog.postgres_schema.large_table (5 TB, 2B rows)
Watermark column: modified_at (TIMESTAMP) or change_seq (BIGINT)

Each run:
  1. Read last_watermark from persisted state
  2. Query: SELECT * FROM large_table WHERE modified_at > :last_watermark
  3. Merge incremental rows into target Delta table (MERGE ON primary key)
  4. Persist new watermark = MAX(modified_at) from this batch
```

### Requirements on the Source System

| Requirement | Why |
| --- | --- |
| Reliable monotonic column (timestamp or auto-increment) | Guarantees no rows are missed between reads |
| Column is indexed | Prevents full-table scan on the source for each incremental query |
| No backdated updates (or acceptable lag window) | Updates that set `modified_at` to an older value will be missed |
| Soft deletes (or CDC complement) | Hard deletes cannot be detected via watermark alone |

### Limitations of Pure Watermark Approach

* **Cannot detect hard deletes** — if a row is physically deleted from the source, the watermark query never sees it. Requires either soft-delete flag or periodic full reconciliation.
* **Backdated timestamps** — if the source allows `UPDATE ... SET modified_at = '2020-01-01'`, the change is invisible to future watermark queries.
* **Clock skew** — distributed source systems may produce out-of-order timestamps across replicas.

### Alternatives Considered

| Approach | Pros | Cons |
| --- | --- | --- |
| UC4 Snapshot (full read) | Simple, handles deletes | Impractical at TB scale for federated sources |
| Source-side CDC → CloudFiles (UC1/UC5 pattern) | Real-time, handles deletes, proven | Requires CDC enabled on source + connector (Debezium/Fivetran/Lakeflow Connect) |
| Lakeflow Connect managed ingestion | Fully managed, watermark handled internally | Limited to supported connectors; less customizable |
| **Watermark-based (this proposal)** | No source-side infrastructure changes needed | Cannot detect deletes; requires monotonic column |

## Proposed Implementation in SDP-META

### Option A: New `source_format` Value

Add `"source_format": "jdbc_incremental"` with new source_details fields:

```json
{
  "data_flow_id": "1000",
  "data_flow_group": "uc10_watermark",
  "source_format": "jdbc_incremental",
  "source_details": {
    "jdbc_url_secret_scope": "sdp_meta_jdbc",
    "jdbc_url_secret_key": "postgres_connection_string",
    "source_database": "public",
    "source_table": "large_transactions",
    "watermark_column": "modified_at",
    "watermark_type": "timestamp",
    "primary_keys": ["transaction_id"]
  },
  "bronze_catalog_dev": "{uc_catalog_name}",
  "bronze_database_dev": "{bronze_schema}",
  "bronze_table": "large_transactions",
  "bronze_cdc_apply_changes": {
    "keys": ["transaction_id"],
    "sequence_by": "modified_at",
    "scd_type": "1"
  }
}
```

### Option B: Lakehouse Federation + Streaming Table with Watermark

Use Lakehouse Federation to expose the OLTP as a foreign catalog, then configure a pipeline that reads incrementally using Spark's JDBC streaming with watermark tracking.

### Option C: Hybrid — Lakeflow Connect for Ingestion, SDP-META for Transformation

Use Lakeflow Connect to handle the incremental JDBC read (it manages watermarks internally), landing raw data as a streaming table. Then use SDP-META's existing silver layer patterns (CDC, fanout, DQE) for downstream transformations.

## Impact Assessment

### Framework Changes Required (Option A)

| Component | Change |
| --- | --- |
| `onboard.py` | Parse new `jdbc_incremental` source_format; validate watermark fields |
| `dataflow_spec.py` | Add watermark fields to `BronzeDataflowSpec` |
| `pipeline_readers.py` | New `read_jdbc_incremental()` method with watermark state management |
| `dataflow_pipeline.py` | Route `jdbc_incremental` format to new reader |
| `variables.yml` | Optional: add JDBC-related variables |
| `sdp_meta_pipelines.yml` | Add UC10 pipeline declaration |
| `onboarding_all_usecases.json` | Add UC10 entry |

### Framework Changes Required (Option C — Recommended)

| Component | Change |
| --- | --- |
| None in framework | Lakeflow Connect handles ingestion independently |
| `onboarding_all_usecases.json` | Add silver-only entry reading from the Connect-managed table |
| `sdp_meta_pipelines.yml` | Add silver pipeline that reads from Connect's output table |

## Recommendation

**Option C (Hybrid)** is recommended for production use:
* Lakeflow Connect is purpose-built for JDBC incremental reads with watermark tracking
* SDP-META remains focused on its strength: metadata-driven transformations, DQE, CDC, and orchestration
* No framework code changes required — just configuration
* Handles deletes (Connect supports CDC mode for supported databases)

**Option A** is appropriate when:
* The source connector is not supported by Lakeflow Connect
* Full control over the watermark logic is required (e.g., custom query predicates)
* The team prefers a single framework for both ingestion and transformation

## Next Steps

- [ ] Validate that Lakeflow Connect supports the target source database
- [ ] Prototype Option C with a single table to measure latency and resource consumption
- [ ] If Option A is chosen, create a design doc for `pipeline_readers.py` changes
- [ ] Add UC10 test data and onboarding entry once approach is finalized

---

*Proposed by: Genie Code | Date: 2025*
*Related discussion: init_sdp_meta_pipeline_snapshot.py, UC4 snapshot limitations*
