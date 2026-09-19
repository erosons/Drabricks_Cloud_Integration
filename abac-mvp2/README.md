# ABAC MVP2 — Scalable Governance Framework

> Configuration-driven, tag-based data governance for **2000+ tables** on Databricks Lakehouse.

---

## Table of Contents

1. [Overview](#overview)
2. [Key Improvements over MVP1](#key-improvements-over-mvp1)
3. [Repository Structure](#repository-structure)
4. [Architecture](#architecture)
5. [Multi-File Config Model](#multi-file-config-model)
6. [Template System](#template-system)
7. [Auto-Discovery](#auto-discovery)
8. [Parallel Execution](#parallel-execution)
9. [Governance App (UI)](#governance-app-ui)
10. [Compliance Dashboard](#compliance-dashboard)
11. [Deployment Guide](#deployment-guide)
12. [Testing](#testing)

---

## Overview

This framework implements a **scalable separation-of-concerns governance model** where:

- **Policies** (what rules to enforce) are defined centrally in `policies.yaml`
- **Securables** (where to enforce them) are split across domain-specific YAML files
- **Templates** reduce repetition via column pattern matching
- **Auto-discovery** onboards brownfield tables from `information_schema`
- **Parallel execution** handles 2000+ tables using `ThreadPoolExecutor`
- **App layer** allows non-technical users to manage principals and grants
- **Dashboard** tracks drift detection for compliance reporting

### Key Principles

| Principle | Implementation |
| --- | --- |
| Configuration-driven | All policies defined in YAML, not ad-hoc SQL |
| Multi-file scalability | Domain teams own their table configs independently |
| Template inheritance | 5 archetypes reduce 50-line definitions to ~8 lines |
| Auto-discovery | Brownfield tables onboarded from information_schema |
| Parallel execution | 20 workers, batches of 50, retry-on-failure |
| Self-service UI | Gradio app for principal/grant management |
| Compliance visibility | Dashboard tracks drift across all tables |
| Idempotent & safe | Safe to run repeatedly without side effects |

---

## Key Improvements over MVP1

| Feature | MVP1 (abac/) | MVP2 (abac-mvp2/) |
| --- | --- | --- |
| Config model | Single `securables.yaml` | Multi-file `securables/**/*.yaml` |
| Table capacity | 1-10 tables | 2000+ tables |
| Column tags | Manually listed per column | Regex pattern matching via templates |
| Execution | Sequential | Parallel (ThreadPoolExecutor) |
| Onboarding | Manual config writing | Auto-discovery from information_schema |
| Principal mgmt | Edit YAML directly | Gradio App (self-service) |
| Drift visibility | Print output | Delta table + Dashboard |
| Validation | Full scan | Sample-based (configurable N) |
| Deployment | DAB (basic) | DAB with app + multi-target |

---

## Repository Structure

```
abac-mvp2/
├── README.md                              # This file
├── databricks.yaml                        # DAB deployment manifest (jobs + app)
├── main (notebook)                        # Orchestrator entry point
├── configs/
│   ├── policies.yaml                      # Central policy definitions (v2)
│   └── securables/
│       ├── _templates.yaml                # Table archetypes (5 templates)
│       ├── _defaults.yaml                 # Catalog/schema defaults + auto-discover rules
│       ├── customer/
│       │   ├── customer_profile.yaml      # ~8 lines (template: standard_pii_table)
│       │   └── customer_addresses.yaml
│       └── finance/
│           └── transactions.yaml
├── src/
│   ├── config_loader.py                   # Core library: loader, resolver, executor
│   └── notebooks/
│       ├── 01b_auto_discover_tables       # Discover + generate config stubs
│       ├── 02_apply_governed_tags         # Parallel tag application
│       ├── 03_deploy_masking_udfs         # Deploy UDFs from registry
│       ├── 03b_grant_rbac_permissions     # Parallel RBAC grants
│       ├── 04_create_abac_policies        # Parallel CREATE POLICY
│       ├── 05_validate_enforcement        # Sample-based masking validation
│       └── 06_drift_detection             # Drift -> Delta for dashboard
├── app/
│   ├── app.yaml                           # Databricks App config
│   └── app.py                             # Gradio UI for policy management
└── test/
    └── 00_setup_100_test_tables           # Creates 100 synthetic PII tables
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                        ABAC MVP2 ARCHITECTURE                                │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────┐    ┌──────────────────────┐    ┌─────────────────┐  │
│  │  configs/           │    │  src/config_loader.py │    │  Unity Catalog  │  │
│  │  policies.yaml      │───▶│  ABACConfigLoader     │───▶│  (2000+ tables) │  │
│  │  securables/**/*.yaml│    │  TemplateResolver     │    │  Tags/Policies  │  │
│  │  _templates.yaml    │    │  ParallelExecutor     │    │  UDFs/Grants    │  │
│  └────────────────────┘    └──────────────────────┘    └─────────────────┘  │
│           ▲                                                     │           │
│           │                                                     ▼           │
│  ┌────────────────────┐                              ┌─────────────────┐    │
│  │  app/app.py         │                              │  Delta Tables   │    │
│  │  (Gradio UI)        │                              │  drift_results  │    │
│  │  - Manage TO/EXCEPT │                              │  run_summary    │    │
│  │  - Manage Grants    │                              │  policy_changes │    │
│  └────────────────────┘                              └────────┬────────┘    │
│                                                               │             │
│                                                     ┌─────────▼────────┐    │
│                                                     │  Dashboard       │    │
│                                                     │  Compliance View │    │
│                                                     └──────────────────┘    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## Multi-File Config Model

### Before (MVP1 — single file)
```yaml
# securables.yaml — 2000+ tables = 40,000+ lines
tables:
  - table_id: customer_profile
    catalog: general_use
    schema: customer
    columns:
      - name: email
        type: STRING
        tags: {class.email_address: ""}
      - name: phone_number
        type: STRING
        tags: {class.phone_number: ""}
      # ... 10+ more columns
  # ... repeat 2000 times
```

### After (MVP2 — domain-split with templates)
```yaml
# configs/securables/customer/customer_profile.yaml — 8 lines
table_id: customer_profile
catalog: general_use
schema: customer
template: standard_pii_table    # Auto-tags email, phone, ssn by column name
policy_bindings:
  - active_records_only
  - ssn_full_redaction
column_overrides:
  - name: region_code
    tags: {region_identifier: ""}
```

The config loader globs `configs/securables/**/*.yaml` (excluding `_` prefixed meta-files) and merges everything into a unified `GovernanceManifest`.

---

## Template System

5 built-in templates in `_templates.yaml`:

| Template | Use Case | Auto-tags |
| --- | --- | --- |
| `standard_pii_table` | General tables with PII | email, phone, ssn, dob, name, address, IP, IBAN |
| `internal_analytics_table` | BI/analytics tables | email, region |
| `sensitive_hr_table` | HR/compensation data | All PII + department + salary |
| `financial_table` | Payment/banking data | email, credit card, IBAN, name |
| `public_reference_table` | Non-sensitive dimensions | None (broad read access) |

Column patterns use **regex matching** against actual column names:
```yaml
column_patterns:
  - match: "^email$|^email_address$|^user_email$|^contact_email$"
    tags: {class.email_address: ""}
```

---

## Auto-Discovery

For brownfield onboarding, define rules in `_defaults.yaml`:

```yaml
auto_discover:
  - catalog: general_use
    schema: customer
    apply_template: standard_pii_table
    exclude_tables: ["_staging_*", "_tmp_*", "_raw_*"]
```

The `01b_auto_discover_tables` notebook queries `information_schema`, finds tables without explicit config files, and generates YAML stubs automatically.

---

## Parallel Execution

`ParallelGovernanceExecutor` in `config_loader.py` handles:

- **Batch size**: 50 tables per batch (configurable)
- **Workers**: 20 parallel threads (configurable)
- **Retry**: Up to 3 retries on transient failures
- **Throughput**: ~100 tables/sec for tag operations

Configure in `policies.yaml`:
```yaml
controls:
  reconciliation:
    max_parallel_workers: 20
    batch_size: 50
    retry_on_failure: true
    max_retries: 3
```

---

## Governance App (UI)

A **Gradio** app for non-technical users to manage policies without editing YAML:

**Capabilities:**
- View policy details (description, scope, UDF, principals)
- Add/remove groups from TO list (who the policy enforces on)
- Add/remove groups from EXCEPT list (who bypasses the policy)
- Add/remove RBAC grants on table configs
- View change audit log

**Deploy:**
```bash
databricks bundle deploy --target dev
# App available at: https://<workspace>/apps/abac-governance-manager
```

---

## Compliance Dashboard

The drift detection notebook writes to Delta tables consumed by an AI/BI Dashboard:

- `general_use.platform_admin.abac_drift_results` — individual findings
- `general_use.platform_admin.abac_drift_run_summary` — per-run aggregates

**Dashboard widgets:**
- Unresolved HIGH findings (counter)
- Compliance % (counter)
- Findings over time (line chart)
- Finding type distribution (bar chart)
- Drift by schema (bar chart)
- Top 20 unresolved findings (detail table)

---

## Deployment Guide

### Prerequisites
- Unity Catalog enabled workspace
- `platform_governance_admin` group with catalog owner permissions
- Governed tags (`class.*`) already created in workspace tag registry

### Quick Start

```bash
# 1. Validate bundle
databricks bundle validate --target dev

# 2. Deploy infrastructure
databricks bundle deploy --target dev

# 3. Run test setup (creates 100 synthetic tables)
databricks bundle run governance_test_setup --target dev

# 4. Run full governance pipeline
databricks bundle run governance_deploy --target dev

# 5. Check drift (also runs daily on schedule)
databricks bundle run governance_drift_check --target dev
```

### Targets

| Target | Catalog | Purpose |
| --- | --- | --- |
| dev | `dev_general_use` | Development/testing |
| staging | `staging_general_use` | Pre-production validation |
| prod | `general_use` | Production enforcement |

---

## Testing

The `test/00_setup_100_test_tables` notebook creates 100 synthetic tables:
- 50 in `customer` schema (standard_pii_table template)
- 30 in `finance` schema (financial_table template)
- 20 in `hr` schema (sensitive_hr_table template)

Each table has randomized PII columns matching template patterns, allowing full pipeline testing.

```bash
# Run test setup
databricks bundle run governance_test_setup --target dev

# Run auto-discovery (should find the 100 tables)
databricks bundle run governance_deploy --target dev

# Verify drift detection
databricks bundle run governance_drift_check --target dev
```

---

## Contributing

### Adding a new table

1. Create `configs/securables/<domain>/<table_name>.yaml`
2. Reference an existing template or specify column_overrides
3. Add policy_bindings if needed beyond inherited defaults
4. Run the deployment pipeline

### Adding a new template

1. Add to `configs/securables/_templates.yaml`
2. Define column_patterns and default_grants
3. Reference from table configs via `template: your_template_name`

### Adding a new policy

1. Define UDF in `policies.yaml` → `udf_registry`
2. Define policy in `policies.yaml` → `policies.row_filters` or `policies.column_masks`
3. Bind to securables via `policy_bindings` at catalog/schema/table level
