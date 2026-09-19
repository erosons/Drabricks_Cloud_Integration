# Databricks Unity Catalog — ABAC Policy Framework

Terraform implementation of Attribute-Based Access Control (ABAC)
for Databricks Unity Catalog, covering 40 data domains × 4 environments
with dynamic row filtering, column masking, and use-case group switching.

---

## Architecture summary

```
Account groups (IDP-synced)
  ├── Structural groups  → USE CATALOG / SCHEMA privileges (static)
  └── Functional groups  → read by row filter / col mask fns at query time (dynamic)

Per-catalog policy objects  (in _policies schema)
  ├── row_filter_{table}_{archetype}()   → returns BOOLEAN, scopes visible rows
  └── col_mask_pii_{domain}()            → returns masked/hashed/null column value
      col_mask_financial_{domain}()

Table registration  (once per table, never changed)
  ├── ALTER TABLE ... SET ROW FILTER ...
  └── ALTER TABLE ... ALTER COLUMN ... SET MASK ...
```

---

## Project structure

```
.
├── providers.tf                        Account + workspace provider config
├── variables.tf                        All input variables
├── locals.tf                           Naming conventions
├── main.tf                             Root module orchestration
├── outputs.tf                          Deployment outputs
│
├── modules/
│   ├── access_groups/                  Account-level group creation
│   ├── catalog/                        Catalog + schema + USE grants
│   ├── row_filters/                    Row filter SQL functions
│   ├── column_masks/                   Column mask SQL functions
│   └── table_grants/                   SELECT + filter/mask attachment
│
├── environments/
│   ├── dev/dev.tfvars
│   ├── qa/qa.tfvars
│   ├── uat/uat.tfvars
│   └── prd/prd.tfvars
│
├── scripts/
│   ├── deploy.sh                       Environment deployment wrapper
│   └── scim_group_manager.py           Dynamic group membership tool
│
├── access_requests/
│   └── example_q1_onboarding.yaml      Bulk access change template
│
├── notebooks/
│   └── validate_abac_policies.sql      Post-deploy validation queries
│
└── .github/workflows/
    └── deploy_abac.yml                 CI/CD pipeline
```

---

## Prerequisites

- Terraform >= 1.5.0
- Databricks provider >= 1.38.0
- Unity Catalog enabled on the account
- Two service principals:
  - Account-level SP: account admin, used for group creation
  - Workspace-level SP: workspace admin, used for catalogs/grants/functions
- S3 bucket (or Azure Storage) for Terraform state
- DynamoDB table for state locking

---

## Quick start

### 1. Configure secrets

Set these as environment variables or GitHub Actions secrets:

```bash
export DATABRICKS_ACCOUNT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
export DATABRICKS_ACCOUNT_CLIENT_ID=...
export DATABRICKS_ACCOUNT_CLIENT_SECRET=...
export DATABRICKS_WORKSPACE_CLIENT_ID=...
export DATABRICKS_WORKSPACE_CLIENT_SECRET=...
```

### 2. Deploy to dev

```bash
./scripts/deploy.sh dev plan    # review changes
./scripts/deploy.sh dev apply   # apply
```

### 3. Promote through environments

```bash
git tag v1.0.0 && git push --tags
# GitHub Actions will:
#   auto-apply qa
#   prompt for approval → apply uat
#   prompt for approval → apply prd
```

### 4. Add a new table

Edit `environments/prd/prd.tfvars` — add one block to the relevant domain:

```hcl
{
  table_name        = "new_table"
  schema_name       = "core"
  row_filter_type   = "region_scoped"
  row_filter_col    = "region"
  pii_columns       = ["col_a"]
  financial_columns = []
}
```

`terraform plan` shows: 1 new filter function, 1 SELECT grant, 1 mask attachment.

---

## Row filter archetypes

| `row_filter_type`  | Functional groups created                                   |
|--------------------|-------------------------------------------------------------|
| `region_scoped`    | `{env}_{domain}_{table}_region_{apac\|emea\|amer\|global}`  |
| `entity_scoped`    | `{env}_{domain}_{table}_{bu_retail\|bu_wholesale\|…}`       |
| `classification`   | `{env}_{domain}_{table}_class_{public\|internal\|…}`        |
| `none`             | No row filter attached                                      |

---

## Dynamic use-case switching

No Terraform changes needed. Use the SCIM manager:

```bash
# Move a user from APAC-only to global coverage
python scripts/scim_group_manager.py switch \
  --user alice@company.com \
  --from prd_finance_ledger_region_apac \
  --to   prd_finance_ledger_region_global

# Audit current access
python scripts/scim_group_manager.py audit \
  --user alice@company.com

# Bulk onboarding from YAML
python scripts/scim_group_manager.py bulk \
  --file access_requests/example_q1_onboarding.yaml \
  --dry-run
```

---

## Exempt groups

| Group                  | Purpose                                              |
|------------------------|------------------------------------------------------|
| `dlt_pipeline_exempt`  | DLT pipeline SP — reads full dataset for MV/ST       |
| `time_travel_exempt`   | Audit users — bypass filter for historical snapshots |

Members of these groups always pass through row filters unconditionally.
Membership must be tightly controlled and audited.

---

## Validation

After deploy, run `notebooks/validate_abac_policies.sql` in your workspace:

- Confirms row filters are attached to all tables
- Confirms PII/financial column masks are attached
- Detects ungated tables (no row filter in production catalogs)
- Detects PII-tagged columns without a mask
- Shows full grant inventory

---

## Key constraints handled

| Constraint                              | How this framework handles it                         |
|-----------------------------------------|-------------------------------------------------------|
| MV / Streaming Table policy requirement | `dlt_pipeline_exempt` group passes through all filters|
| Time travel + ABAC conflict             | `time_travel_exempt` group bypasses all row filters   |
| 40 domains × 100 tables scale           | Single `domain_tables` variable drives all resources  |
| No DDL change on access switch          | Group membership change only — filter evaluates live  |
| Cross-domain access                     | User joins structural groups of multiple domains      |
| Environment promotion                   | Same TF code, catalog prefix parameterised by env     |
