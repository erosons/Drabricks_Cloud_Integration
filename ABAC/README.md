# ABAC/GBAC Governance Framework for Unity Catalog

> Configuration-driven, tag-based data governance for Databricks Lakehouse.

---

## Table of Contents

1. [Overview](#overview)
2. [Repository Structure](#repository-structure)
3. [Architecture Layers](#architecture-layers)
4. [Architecture Flow Diagram](#architecture-flow-diagram)
5. [Sequence Diagrams](#sequence-diagrams)
6. [Configuration Separation Model](#configuration-separation-model)
7. [Governed Tag Strategy](#governed-tag-strategy)
8. [Deployment Guide](#deployment-guide)
9. [Testing Strategy](#testing-strategy)

---

## Overview

This framework implements a **separation-of-concerns governance model** where:

- **Policies** (what rules to enforce) are defined independently of
- **Securables** (where to enforce them)

The reconciliation engine reads both configurations and applies the correct
ABAC policies, governed tags, masking UDFs, and RBAC grants to Unity Catalog.

### Key Principles

| Principle | Implementation |
| --- | --- |
| Configuration-driven | All policies defined in YAML, not ad-hoc SQL |
| Use existing governed tags | Leverages workspace `class.*` tags (email, phone, DOB) |
| Tag-first enforcement | ABAC policies match columns by tag, not by name |
| Deny-by-default | `All Users` are masked; exceptions require group membership |
| Idempotent deployment | Safe to run repeatedly without side effects |
| Separation of concerns | Policies vs securables vs deployment are independent |

---

## Repository Structure

```
ABAC/
├── README.md                              # This file
├── configs/
│   ├── policies.yaml                      # Layer 1: Policy definitions
│   └── securables.yaml                    # Layer 2: UC data targets + tag assignments
├── bundle/
│   ├── databricks.yaml                    # Layer 3: DAB deployment manifest
│   └── notebooks/
│       ├── 01_setup_test_data.py          # Create synthetic PII test table
│       ├── 02_apply_governed_tags.py      # Apply class.* tags to columns
│       ├── 03_deploy_masking_udfs.py      # Deploy mask_email, mask_phone, mask_dob
│       ├── 04_create_abac_policies.py     # CREATE POLICY with MATCH COLUMNS
│       ├── 05_validate_enforcement.py     # Verify masking works at runtime
│       ├── 06_drift_detection.py          # Scheduled drift checks
│       └── 99_teardown.py                 # Clean teardown for re-testing
├── governance_reconciliation_engine       # Layer 4: Enterprise reconciliation notebook
└── governance_validation_tests            # Layer 5: Validation & audit notebook
```

---

## Architecture Layers

### Layer 1: Policy Registry (`configs/policies.yaml`)

**Purpose:** Define WHAT rules to enforce — independent of any specific table.

```
┌─────────────────────────────────────────────────────────────┐
│                    POLICY REGISTRY                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────┐  ┌──────────────────┐                 │
│  │  Governed Tags  │  │  Group Templates │                 │
│  │  (references)   │  │  (GBAC naming)   │                 │
│  └────────┬────────┘  └────────┬─────────┘                 │
│           │                    │                            │
│  ┌────────▼────────┐  ┌───────▼──────────┐                 │
│  │  UDF Registry   │  │  ABAC Policies   │                 │
│  │  - mask_email   │  │  - TO principals │                 │
│  │  - mask_phone   │  │  - EXCEPT groups │                 │
│  │  - mask_dob     │  │  - MATCH COLUMNS │                 │
│  └─────────────────┘  └──────────────────┘                 │
│                                                             │
│  ┌─────────────────┐  ┌──────────────────┐                 │
│  │  Access Request │  │  Controls &      │                 │
│  │  Workflows      │  │  Guardrails      │                 │
│  └─────────────────┘  └──────────────────┘                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Contents:**

| Section | Purpose |
| --- | --- |
| `governed_tags` | References to EXISTING workspace tags (`class.email_address`, etc.) |
| `group_templates` | GBAC naming patterns and role-to-privilege mappings |
| `udf_registry` | Row filter and column mask function definitions |
| `policies` | ABAC rule declarations (scope, principals, tag matching) |
| `access_request` | Approval workflow chains and expiration rules |
| `controls` | Deployment guardrails, fail-closed behavior, audit settings |

---

### Layer 2: Securables Registry (`configs/securables.yaml`)

**Purpose:** Define WHERE to enforce — the UC objects, their tags, and policy bindings.

```
┌─────────────────────────────────────────────────────────────┐
│                   SECURABLES REGISTRY                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  CATALOG: general_use                                │   │
│  │    tags: governance.classification = internal        │   │
│  │    policy_bindings: [pii_email_masking, ...]         │   │
│  │                                                      │   │
│  │  ┌───────────────────────────────────────────────┐  │   │
│  │  │  SCHEMA: customer                             │  │   │
│  │  │    tags: governance.domain = customer          │  │   │
│  │  │    policy_bindings: [regional_data_isolation]  │  │   │
│  │  │                                               │  │   │
│  │  │  ┌─────────────────────────────────────────┐  │  │   │
│  │  │  │  TABLE: customer_profile                │  │  │   │
│  │  │  │    groups: reader, editor, masked, ...  │  │  │   │
│  │  │  │    grants: [USE CATALOG, SELECT, ...]   │  │  │   │
│  │  │  │                                        │  │  │   │
│  │  │  │  COLUMNS:                              │  │  │   │
│  │  │  │    email        → class.email_address  │  │  │   │
│  │  │  │    phone_number → class.phone_number   │  │  │   │
│  │  │  │    date_of_birth→ class.date_of_birth  │  │  │   │
│  │  │  └─────────────────────────────────────────┘  │  │   │
│  │  └───────────────────────────────────────────────┘  │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌──────────────────────┐  ┌────────────────────────────┐  │
│  │  Denied Columns      │  │  Publication Requirements  │  │
│  │  (full redaction)    │  │  (mandatory tags/groups)   │  │
│  └──────────────────────┘  └────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Contents:**

| Section | Purpose |
| --- | --- |
| `catalogs` | Top-level UC catalogs with tags and policy bindings |
| `schemas` | Domain boundaries with inherited defaults |
| `tables` | Data products with columns, groups, grants |
| `denied_columns` | Fully redacted columns for specific groups |
| `publication_requirements` | Mandatory tags before a product goes live |

---

### Layer 3: DAB Bundle (`bundle/databricks.yaml`)

**Purpose:** Declarative Automation Bundle for CI/CD deployment and testing.

```
┌─────────────────────────────────────────────────────────────┐
│                    DAB BUNDLE                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TARGETS: dev → staging → prod                              │
│                                                             │
│  JOB: governance_deploy (5-task pipeline)                   │
│    01_setup_test_data ──→ 02_apply_governed_tags            │
│         ──→ 03_deploy_masking_udfs ──→ 04_create_policies   │
│              ──→ 05_validate_enforcement                    │
│                                                             │
│  JOB: governance_drift_check (daily scheduled)              │
│    06_drift_detection (cron: 0 0 8 * * ?)                   │
│                                                             │
│  JOB: governance_teardown (on-demand)                       │
│    99_teardown (removes all for clean re-run)               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Variables (per target):**

| Variable | dev | staging | prod |
| --- | --- | --- | --- |
| `governance_catalog` | governance_dev | governance | governance |
| `test_catalog` | dev_general_use | staging_general_use | general_use |
| `test_schema` | customer_test | customer | customer |

---

### Layer 4: Reconciliation Engine (notebook)

**Purpose:** Enterprise-scale engine that reads BOTH config files and generates/applies UC SQL.

```
┌─────────────────────────────────────────────────────────────┐
│              RECONCILIATION ENGINE                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  INPUT:                                                     │
│    policies.yaml + securables.yaml                          │
│                                                             │
│  PROCESSING:                                                │
│    1. Validate cross-references                             │
│    2. Resolve policy_bindings → scope targets               │
│    3. Resolve {domain}_{product} principal templates        │
│    4. Detect conflicts (multiple filters/masks)             │
│                                                             │
│  OUTPUT (ordered):                                          │
│    Step 1: Governed tag SDK code                            │
│    Step 2: CREATE FUNCTION statements (UDFs)                │
│    Step 3: SET TAG ON COLUMN statements                     │
│    Step 4: Group creation SDK code                          │
│    Step 5: GRANT statements (RBAC)                          │
│    Step 6: CREATE POLICY statements (ABAC)                  │
│                                                             │
│  MODES:                                                     │
│    dry_run → generates SQL for review                       │
│    apply   → executes against UC                            │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### Layer 5: Validation & Testing (notebook)

**Purpose:** Runtime validation, drift detection, and audit queries.

```
┌─────────────────────────────────────────────────────────────┐
│              VALIDATION & TESTING                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  POLICY INSPECTION                                          │
│    SHOW POLICIES ON CATALOG/SCHEMA/TABLE                    │
│    SHOW EFFECTIVE POLICIES ON TABLE                          │
│    DESCRIBE POLICY                                          │
│                                                             │
│  DRIFT DETECTION                                            │
│    Compare column tags (information_schema) vs config        │
│    Compare active policies vs expected policies             │
│    Report: TAG_MISSING, VALUE_MISMATCH, POLICY_MISSING      │
│                                                             │
│  TEST GENERATION                                            │
│    Auto-generate test matrix from config:                   │
│    - Positive (reader SELECT, editor MODIFY)                │
│    - Negative (no group = denied)                           │
│    - Masking (masked_reader sees ***)                       │
│    - Cleartext (exception group sees real values)           │
│                                                             │
│  AUDIT QUERIES                                              │
│    system.access.audit: policy changes, tag changes,        │
│    grant changes, denied access events                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Architecture Flow Diagram

```
                    ┌──────────────────────┐
                    │   Data Producer /    │
                    │   Product Owner      │
                    └──────────┬───────────┘
                               │
                               ▼
              ┌────────────────────────────────┐
              │   GOVERNANCE INTAKE            │
              │   Define data product,         │
              │   sensitivity, consumers       │
              └────────────────┬───────────────┘
                               │
               ┌───────────────┼───────────────┐
               │               │               │
               ▼               ▼               ▼
     ┌─────────────┐  ┌──────────────┐  ┌─────────────┐
     │ policies.   │  │ securables.  │  │ databricks. │
     │ yaml        │  │ yaml         │  │ yaml        │
     │             │  │              │  │             │
     │ - UDFs      │  │ - Catalogs   │  │ - Jobs      │
     │ - ABAC rules│  │ - Schemas    │  │ - Targets   │
     │ - Groups    │  │ - Tables     │  │ - Variables │
     │ - Controls  │  │ - Columns    │  │ - Schedule  │
     │             │  │ - Tags       │  │             │
     └──────┬──────┘  └──────┬───────┘  └──────┬──────┘
            │                │                  │
            └────────┬───────┘                  │
                     │                          │
                     ▼                          ▼
     ┌───────────────────────────┐   ┌──────────────────────┐
     │  RECONCILIATION ENGINE    │   │  DAB BUNDLE DEPLOY   │
     │                           │   │  databricks bundle   │
     │  1. Validate configs      │   │  deploy --target dev │
     │  2. Resolve bindings      │   └──────────┬───────────┘
     │  3. Generate SQL          │              │
     │  4. Apply (or dry-run)    │              │
     └─────────────┬─────────────┘              │
                   │                            │
                   └──────────┬─────────────────┘
                              │
                              ▼
     ┌─────────────────────────────────────────────────────┐
     │              UNITY CATALOG                           │
     ├─────────────────────────────────────────────────────┤
     │                                                     │
     │  ┌───────────┐  ┌───────────┐  ┌────────────────┐  │
     │  │ Governed  │  │ Masking   │  │ ABAC Policies  │  │
     │  │ Tags      │  │ UDFs      │  │                │  │
     │  │           │  │           │  │ mask_email_    │  │
     │  │ class.    │  │ mask_     │  │ policy         │  │
     │  │ email_    │  │ email()   │  │                │  │
     │  │ address   │  │ mask_     │  │ mask_phone_    │  │
     │  │ class.    │  │ phone()   │  │ policy         │  │
     │  │ phone_    │  │ mask_     │  │                │  │
     │  │ number    │  │ dob()     │  │ mask_dob_      │  │
     │  │ class.    │  │           │  │ policy         │  │
     │  │ date_of_  │  │           │  │                │  │
     │  │ birth     │  │           │  │                │  │
     │  └───────────┘  └───────────┘  └────────────────┘  │
     │                                                     │
     │  ┌───────────┐  ┌───────────┐                      │
     │  │ RBAC      │  │ Groups    │                      │
     │  │ Grants    │  │ (GBAC)    │                      │
     │  │           │  │           │                      │
     │  │ SELECT    │  │ _reader   │                      │
     │  │ MODIFY    │  │ _editor   │                      │
     │  │ USE       │  │ _masked   │                      │
     │  │ CATALOG   │  │ _cleartext│                      │
     │  └───────────┘  └───────────┘                      │
     │                                                     │
     └──────────────────────────┬──────────────────────────┘
                                │
                                ▼
     ┌─────────────────────────────────────────────────────┐
     │              QUERY-TIME ENFORCEMENT                  │
     ├─────────────────────────────────────────────────────┤
     │                                                     │
     │  User Query: SELECT email, phone, date_of_birth     │
     │              FROM general_use.customer.customer_     │
     │              profile                                │
     │                                                     │
     │         ┌─────────────────────────────┐             │
     │         │  Is user in cleartext group? │             │
     │         └─────────────┬───────────────┘             │
     │                       │                             │
     │              ┌────────┴────────┐                    │
     │              │                 │                    │
     │              ▼                 ▼                    │
     │         ┌────────┐       ┌──────────┐              │
     │         │  YES   │       │   NO     │              │
     │         └────┬───┘       └────┬─────┘              │
     │              │                │                    │
     │              ▼                ▼                    │
     │  ┌────────────────┐  ┌────────────────────────┐   │
     │  │ Return:        │  │ Return:                │   │
     │  │ alice@mail.com │  │ ***@mail.com           │   │
     │  │ +1-555-0101    │  │ (***) ***-0101         │   │
     │  │ 1985-03-15     │  │ 1985-01-01             │   │
     │  └────────────────┘  └────────────────────────┘   │
     │                                                     │
     └─────────────────────────────────────────────────────┘
```

---

## Sequence Diagrams

### Sequence 1: Policy Deployment (DAB Bundle Run)

```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Engineer │  │  DAB     │  │ 01_setup │  │ 02_tags  │  │ 03_udfs  │  │ 04_abac  │
│          │  │  Runner  │  │          │  │          │  │          │  │          │
└────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘
     │              │              │              │              │              │
     │ bundle run   │              │              │              │              │
     │─────────────>│              │              │              │              │
     │              │              │              │              │              │
     │              │ run task 1   │              │              │              │
     │              │─────────────>│              │              │              │
     │              │              │              │              │              │
     │              │              │─── CREATE TABLE customer_profile ──────>  UC
     │              │              │<── ✓ Table created ────────────────────  UC
     │              │              │              │              │              │
     │              │              │─── INSERT test data ───────────────────> UC
     │              │              │<── ✓ 10 rows inserted ────────────────  UC
     │              │              │              │              │              │
     │              │<── success ──│              │              │              │
     │              │              │              │              │              │
     │              │ run task 2   │              │              │              │
     │              │──────────────────────────>  │              │              │
     │              │              │              │              │              │
     │              │              │              │─── SET TAG ON COLUMN       │
     │              │              │              │    email `class.email_     │
     │              │              │              │    address` ─────────────> UC
     │              │              │              │<── ✓ Tag applied ────────  UC
     │              │              │              │              │              │
     │              │              │              │─── SET TAG ON COLUMN       │
     │              │              │              │    phone `class.phone_     │
     │              │              │              │    number` ─────────────> UC
     │              │              │              │<── ✓ Tag applied ────────  UC
     │              │              │              │              │              │
     │              │              │              │─── SET TAG ON COLUMN       │
     │              │              │              │    dob `class.date_of_     │
     │              │              │              │    birth` ──────────────> UC
     │              │              │              │<── ✓ Tag applied ────────  UC
     │              │              │              │              │              │
     │              │<──────────── success ───────│              │              │
     │              │              │              │              │              │
     │              │ run task 3   │              │              │              │
     │              │───────────────────────────────────────────>│              │
     │              │              │              │              │              │
     │              │              │              │              │─── CREATE OR REPLACE
     │              │              │              │              │    FUNCTION mask_email
     │              │              │              │              │    ─────────────────> UC
     │              │              │              │              │<── ✓ ────────────── UC
     │              │              │              │              │              │
     │              │              │              │              │─── CREATE OR REPLACE
     │              │              │              │              │    FUNCTION mask_phone
     │              │              │              │              │    ─────────────────> UC
     │              │              │              │              │<── ✓ ────────────── UC
     │              │              │              │              │              │
     │              │              │              │              │─── CREATE OR REPLACE
     │              │              │              │              │    FUNCTION mask_dob
     │              │              │              │              │    ─────────────────> UC
     │              │              │              │              │<── ✓ ────────────── UC
     │              │              │              │              │              │
     │              │<──────────────── success ──────────────────│              │
     │              │              │              │              │              │
     │              │ run task 4   │              │              │              │
     │              │──────────────────────────────────────────────────────────>│
     │              │              │              │              │              │
     │              │              │              │              │              │─── CREATE
     │              │              │              │              │              │    POLICY
     │              │              │              │              │              │    mask_
     │              │              │              │              │              │    email_
     │              │              │              │              │              │    policy
     │              │              │              │              │              │    ON SCHEMA
     │              │              │              │              │              │    ──────> UC
     │              │              │              │              │              │<── ✓ ─── UC
     │              │              │              │              │              │
     │              │              │              │              │              │── (repeat
     │              │              │              │              │              │    for phone
     │              │              │              │              │              │    and dob)
     │              │              │              │              │              │
     │              │<─────────────────── success ─────────────────────────────│
     │              │              │              │              │              │
     │<── deployed ─│              │              │              │              │
     │              │              │              │              │              │
```

### Sequence 2: Query-Time Policy Enforcement

```
┌──────────┐         ┌──────────────┐         ┌─────────────────────┐
│  User    │         │ Unity Catalog│         │  Policy Engine      │
│  (Analyst)│         │  (Metastore) │         │  (ABAC Evaluator)   │
└────┬─────┘         └──────┬───────┘         └──────────┬──────────┘
     │                       │                            │
     │  SELECT email,        │                            │
     │  phone_number,        │                            │
     │  date_of_birth        │                            │
     │  FROM customer_profile│                            │
     │──────────────────────>│                            │
     │                       │                            │
     │                       │  Check base privileges     │
     │                       │  (RBAC: USE CATALOG,       │
     │                       │   USE SCHEMA, SELECT)      │
     │                       │──────────┐                 │
     │                       │          │                 │
     │                       │<─────────┘                 │
     │                       │  ✓ Has SELECT              │
     │                       │                            │
     │                       │  Resolve effective         │
     │                       │  policies on table         │
     │                       │───────────────────────────>│
     │                       │                            │
     │                       │                            │  Check column tags:
     │                       │                            │  email → class.email_address
     │                       │                            │  phone → class.phone_number
     │                       │                            │  dob   → class.date_of_birth
     │                       │                            │
     │                       │                            │  Match policies:
     │                       │                            │  mask_email_policy  → email
     │                       │                            │  mask_phone_policy  → phone
     │                       │                            │  mask_dob_policy    → dob
     │                       │                            │
     │                       │                            │  Check principals:
     │                       │                            │  User in `All Users`? YES
     │                       │                            │  User in cleartext
     │                       │                            │  exception group?   NO
     │                       │                            │
     │                       │                            │  → Apply masks
     │                       │                            │
     │                       │  Return mask functions     │
     │                       │<───────────────────────────│
     │                       │                            │
     │                       │  Execute query with        │
     │                       │  mask UDFs wrapping        │
     │                       │  column values             │
     │                       │──────────┐                 │
     │                       │          │                 │
     │                       │<─────────┘                 │
     │                       │                            │
     │  Results:             │                            │
     │  ***@example.com      │                            │
     │  (***) ***-0101       │                            │
     │  1985-01-01           │                            │
     │<──────────────────────│                            │
     │                       │                            │
```

### Sequence 3: Drift Detection (Scheduled)

```
┌──────────┐    ┌──────────────┐    ┌────────────────┐    ┌──────────────┐
│  Cron    │    │ 06_drift_    │    │ information_   │    │  Alert /     │
│  Trigger │    │ detection.py │    │ schema views   │    │  Operator    │
└────┬─────┘    └──────┬───────┘    └───────┬────────┘    └──────┬───────┘
     │                  │                    │                    │
     │  Daily 8AM UTC   │                    │                    │
     │─────────────────>│                    │                    │
     │                  │                    │                    │
     │                  │  Query column_tags │                    │
     │                  │  for each table    │                    │
     │                  │───────────────────>│                    │
     │                  │                    │                    │
     │                  │  Actual tags       │                    │
     │                  │<───────────────────│                    │
     │                  │                    │                    │
     │                  │  Compare vs        │                    │
     │                  │  expected_tags      │                    │
     │                  │  from config       │                    │
     │                  │──────┐             │                    │
     │                  │      │             │                    │
     │                  │<─────┘             │                    │
     │                  │                    │                    │
     │                  │  SHOW POLICIES     │                    │
     │                  │  ON SCHEMA         │                    │
     │                  │───────────────────>│                    │
     │                  │                    │                    │
     │                  │  Active policies   │                    │
     │                  │<───────────────────│                    │
     │                  │                    │                    │
     │                  │  Compare vs        │                    │
     │                  │  expected_policies  │                    │
     │                  │──────┐             │                    │
     │                  │      │             │                    │
     │                  │<─────┘             │                    │
     │                  │                    │                    │
     │                  │                    │                    │
     │                  │  IF drift found:   │                    │
     │                  │  Report drift      │                    │
     │                  │────────────────────────────────────────>│
     │                  │                    │                    │
     │                  │                    │                    │  Remediate
     │                  │                    │                    │  or alert
     │                  │                    │                    │
```

### Sequence 4: Access Request & Approval

```
┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────┐
│  User    │  │  Access      │  │  Product     │  │  Governance  │  │  Unity   │
│  (Requester)│  Request UI  │  │  Owner       │  │  Team        │  │  Catalog │
└────┬─────┘  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘  └────┬─────┘
     │                │                  │                  │              │
     │ Request access │                  │                  │              │
     │ to customer_   │                  │                  │              │
     │ profile        │                  │                  │              │
     │───────────────>│                  │                  │              │
     │                │                  │                  │              │
     │                │  Look up config: │                  │              │
     │                │  approval_chain  │                  │              │
     │                │  = "standard"    │                  │              │
     │                │                  │                  │              │
     │                │  Route to        │                  │              │
     │                │  product_owner   │                  │              │
     │                │─────────────────>│                  │              │
     │                │                  │                  │              │
     │                │                  │  Approve         │              │
     │                │                  │─────────────────>│              │
     │                │                  │                  │              │
     │                │                  │                  │  Validate    │
     │                │                  │                  │  policy      │
     │                │                  │                  │  constraints │
     │                │                  │                  │──────┐       │
     │                │                  │                  │      │       │
     │                │                  │                  │<─────┘       │
     │                │                  │                  │              │
     │                │                  │                  │  Add user to │
     │                │                  │                  │  customer_   │
     │                │                  │                  │  customer_   │
     │                │                  │                  │  profile_    │
     │                │                  │                  │  reader      │
     │                │                  │                  │─────────────>│
     │                │                  │                  │              │
     │                │                  │                  │  ✓ Group     │
     │                │                  │                  │  membership  │
     │                │                  │                  │  updated     │
     │                │                  │                  │<─────────────│
     │                │                  │                  │              │
     │  Access        │                  │                  │              │
     │  granted       │                  │                  │              │
     │  (expires in   │                  │                  │              │
     │   90 days)     │                  │                  │              │
     │<───────────────│                  │                  │              │
     │                │                  │                  │              │
     │  SELECT * FROM customer_profile   │                  │              │
     │──────────────────────────────────────────────────────────────────>  │
     │                │                  │                  │              │
     │  Results (masked per policy)      │                  │              │
     │<─────────────────────────────────────────────────────────────────  │
     │                │                  │                  │              │
```

---

## Configuration Separation Model

The core innovation is separating **policy intent** from **data targets**:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                                                                         │
│   policies.yaml                    securables.yaml                      │
│   ─────────────                    ────────────────                     │
│                                                                         │
│   "Mask any column tagged          "The 'email' column on              │
│    with class.email_address"        customer_profile has tag            │
│                                     class.email_address"                │
│                                                                         │
│         ┌───────────┐                    ┌───────────┐                  │
│         │  WHAT to  │                    │  WHERE to │                  │
│         │  enforce  │                    │  enforce  │                  │
│         └─────┬─────┘                    └─────┬─────┘                  │
│               │                                │                        │
│               └────────────┬───────────────────┘                        │
│                            │                                            │
│                            ▼                                            │
│               ┌────────────────────────┐                                │
│               │  RECONCILIATION ENGINE │                                │
│               │                        │                                │
│               │  Joins policy_bindings │                                │
│               │  to scope targets      │                                │
│               │                        │                                │
│               │  Generates:            │                                │
│               │  CREATE POLICY         │                                │
│               │  mask_email_policy     │                                │
│               │  ON SCHEMA             │                                │
│               │  general_use.customer  │                                │
│               │  COLUMN MASK           │                                │
│               │  governance.policy_    │                                │
│               │  functions.mask_email  │                                │
│               │  TO `All Users`        │                                │
│               │  EXCEPT cleartext grp  │                                │
│               │  FOR TABLES            │                                │
│               │  MATCH COLUMNS         │                                │
│               │  has_tag('class.       │                                │
│               │  email_address')       │                                │
│               │  AS email_col          │                                │
│               │  ON COLUMN email_col   │                                │
│               └────────────────────────┘                                │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Why Separate?

| Benefit | Explanation |
| --- | --- |
| **Reusability** | One policy masks ALL email columns in ALL tables (tag-driven) |
| **Scalability** | Adding a new table only requires securables.yaml + tag assignment |
| **Auditability** | Policy changes are versioned independently from data changes |
| **Team boundaries** | Governance team owns policies; data engineers own securables |
| **Testing** | Policies can be tested in isolation against mock targets |

---

## Governed Tag Strategy

This framework uses **existing** workspace governed tags from the `class.*` namespace:

| Governed Tag | Applied To | ABAC Policy | Mask Behavior |
| --- | --- | --- | --- |
| `class.email_address` | Email columns | `mask_email_policy` | `***@domain.com` |
| `class.phone_number` | Phone columns | `mask_phone_policy` | `(***) ***-XXXX` |
| `class.date_of_birth` | DOB columns | `mask_dob_policy` | `YYYY-01-01` (year only) |
| `class.name` | Name columns | `mask_name_policy` | `F***L` |
| `class.us_ssn` | SSN columns | `mask_ssn_policy` | `***-**-XXXX` |
| `class.credit_card` | Card columns | `mask_credit_card_policy` | `****-****-****-XXXX` |

### How Tag-Based Masking Works

1. **Tag a column** — `SET TAG ON COLUMN table.email \`class.email_address\` = \`\`;`
2. **Policy matches by tag** — `MATCH COLUMNS has_tag('class.email_address') AS email_col`
3. **Mask applied at runtime** — `COLUMN MASK governance.policy_functions.mask_email`
4. **Any NEW column** tagged the same way is **automatically protected**

---

## Deployment Guide

### Prerequisites

- Databricks workspace with Unity Catalog enabled
- Databricks Runtime 16.4+ or serverless compute
- `databricks` CLI authenticated
- Permissions: MANAGE on governance catalog, CREATE TABLE on target schema

### Deploy with DAB Bundle

```bash
# Navigate to the bundle directory
cd ABAC/bundle

# Validate the bundle
databricks bundle validate --target dev

# Deploy resources (creates jobs)
databricks bundle deploy --target dev

# Run the full governance deployment
databricks bundle run governance_deploy --target dev

# Run drift detection manually
databricks bundle run governance_drift_check --target dev

# Clean up for fresh re-test
databricks bundle run governance_teardown --target dev
```

### Deploy with Reconciliation Engine (enterprise)

1. Open `governance_reconciliation_engine` notebook
2. Set `DEPLOYMENT_MODE = "dry_run"` for review
3. Run all cells to generate full SQL script
4. Review generated SQL
5. Set `DEPLOYMENT_MODE = "apply"` and re-run

---

## Testing Strategy

### Test Matrix (auto-generated from config)

| Principal | Group | Table | Sensitive Column | Expected |
| --- | --- | --- | --- | --- |
| Alice | reader | customer_profile | email | Masked: `***@example.com` |
| Bob | masked_reader | customer_profile | phone | Masked: `(***) ***-0101` |
| Carol | cleartext_approved | customer_profile | dob | Cleartext: `1985-03-15` |
| Dave | NO_GROUP | customer_profile | any | DENIED |
| Erin | reader | customer_profile | date_of_birth | Masked: `1985-01-01` |

### Running Tests

```bash
# Via DAB bundle (includes validation step)
databricks bundle run governance_deploy --target dev

# Or run validation notebook directly
# Open: ABAC Governance Validation Tests → Run All
```

### Validation Checks

- **Tag drift**: Compares `information_schema.column_tags` vs config
- **Policy drift**: Compares `SHOW POLICIES` vs expected policies
- **Masking verification**: Queries PII columns and checks for mask patterns
- **Audit trail**: Reviews `system.access.audit` for governance events

---

## Control Flow Summary

```
Governed Tag Applied → ABAC Policy Matches → Mask UDF Executes → User Sees Masked Value
       ↑                       ↑                      ↑                      ↑
  securables.yaml        policies.yaml         policies.yaml          Runtime UC
  (WHERE)                (WHAT rule)           (HOW to mask)          (enforcement)
```

---

## License

Internal governance framework — Databricks Unity Catalog compatible.
