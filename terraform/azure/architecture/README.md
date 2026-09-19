# Azure Databricks Terraform — Architecture Reference

This document explains the full `terraform/azure/` directory: what each root resource and module provisions, how modules call each other, what variables to set per environment, and the apply workflow required for Unity Catalog.

---

## Directory Tree

```
terraform/azure/
├── backend.tf                  # AzureRM remote-state backend (no values — use -backend-config)
├── main.tf                     # Root: VNet, storage, workspace, Unity Catalog, cluster policies
├── providers.tf                # azurerm ~3.0, azuread ~2.0, databricks ~1.0
├── variables.tf                # All root variables (auth, environment, networking, storage, policies)
├── outputs.tf                  # workspace_url, workspace_id, vnet_id, SP credentials
│
├── environments/
│   ├── dev/dev.tfvars          # Dev overrides — 3 domains, smaller table list
│   └── prd/prd.tfvars          # Production overrides — 10+ domains, full table list
│
├── modules/
│   ├── networking/             # VNet, subnets, NSG, private DNS zones
│   ├── storage/                # ADLS Gen2 storage accounts, containers, private endpoints
│   ├── cluster_policies/       # Databricks cluster policies (prod/staging/dev/sql/interactive/job)
│   ├── access_groups/          # ABAC: account-level structural + functional groups
│   ├── catalog/                # Unity Catalog catalog + schemas per domain
│   ├── row_filters/            # SQL row-filter functions in _policies schema
│   ├── column_masks/           # SQL column-mask functions in _policies schema
│   └── table_grants/           # SELECT grants + row filter + column mask attachment per table
│
├── abac/                       # Standalone ABAC deployment (groups → catalogs → filters → grants)
│   ├── providers.tf            # Two provider aliases: databricks.account + databricks.workspace
│   ├── main.tf                 # 5-step module orchestration
│   ├── locals.tf               # Naming conventions, dimension values, tag constants
│   ├── variables.tf            # Environment, domains, domain_tables, SP names
│   ├── outputs.tf
│   └── notebooks/
│       └── validate_abac_policies.sql
│
└── scripts/
    ├── 01_setup_terraform_state.sh   # Bootstrap tfstate storage account
    ├── deploy.sh                     # Wrapper: init → plan → apply per environment
    └── scim_group_manager.py         # Helper: sync Entra ID groups into Databricks
```

---

## Root Module (`terraform/azure/`)

### What it provisions

The root module creates the full platform layer in one shot:

| Resource | What it does |
|---|---|
| `azurerm_resource_group.main` | Container for all Azure resources, named `{env}-{project}-rg` |
| `module.networking` | VNet, two Databricks-delegated subnets, NSG rules, private DNS zones |
| `module.storage` | ADLS Gen2 metastore storage account, optional separate data lake account, private endpoints |
| `azurerm_databricks_workspace.main` | Premium Databricks workspace injected into the VNet |
| `azuread_application/service_principal` | Entra ID SP used by Databricks to authenticate to ADLS |
| `azurerm_role_assignment` | Storage Blob Data Contributor on the metastore storage account |
| `module.cluster_policies` | Up to 6 cluster policies (prod, staging, dev, SQL warehouse, interactive, job) |
| `databricks_metastore.main` | Unity Catalog metastore backed by the ADLS container |
| `databricks_metastore_assignment.workspace` | Attaches the metastore to the workspace |
| `databricks_storage_credential` | Databricks credential using the SP client secret |
| `databricks_external_location` (×2) | External locations for `metastore` and `data` containers |

### How modules are called

```hcl
# 1. Networking — no dependencies
module "networking" {
  source = "./modules/networking"
  environment = var.environment
  vnet_address_space    = var.vnet_address_space
  public_subnet_prefix  = var.public_subnet_prefix
  private_subnet_prefix = var.private_subnet_prefix
  enable_private_endpoints = var.enable_private_endpoints
  ...
}

# 2. Storage — depends on networking (passes private_subnet_id)
module "storage" {
  source = "./modules/storage"
  allowed_subnet_ids       = [module.networking.private_subnet_id]
  private_subnet_id        = module.networking.private_subnet_id
  blob_private_dns_zone_name = module.networking.blob_private_dns_zone_name
  depends_on = [module.networking]
}

# 3. Workspace — depends on networking (VNet injection)
resource "azurerm_databricks_workspace" "main" {
  custom_parameters {
    virtual_network_id  = module.networking.vnet_id
    subnet_name_public  = module.networking.public_subnet_name
    subnet_name_private = module.networking.private_subnet_name
    public_subnet_network_security_group_association_id  = module.networking.public_nsg_association_id
    private_subnet_network_security_group_association_id = module.networking.private_nsg_association_id
  }
  depends_on = [module.networking]
}

# 4. Cluster policies — depends on workspace being provisioned
module "cluster_policies" {
  source = "./modules/cluster_policies"
  depends_on = [azurerm_databricks_workspace.main]
}

# 5. Metastore — depends on storage (ADLS URL) and workspace
resource "databricks_metastore" "main" {
  storage_root = "abfss://{container}@{module.storage.metastore_storage_account_name}.dfs.core.windows.net/"
  depends_on   = [module.storage, azurerm_databricks_workspace.main]
}
```

### Dependency graph

```
networking ──► storage ──────────────────────────────► metastore
           └──► workspace ──► cluster_policies          │
                          └──────────────────────────► metastore_assignment
                                                        │
                                                        storage_credential
                                                        │
                                                        external_location (×2)
```

---

## Module Reference

### `modules/networking`

**Purpose:** VNet injection layer for Databricks.

**Resources created:**
- `azurerm_virtual_network` — named `{env}-{project}-vnet`
- `azurerm_subnet.public` + `azurerm_subnet.private` — both delegated to `Microsoft.Databricks/workspaces`; service endpoints: Storage, KeyVault, SQL
- `azurerm_network_security_group` — 3 rules: allow VNet inbound, allow AzureCloud outbound, allow HTTPS outbound
- `azurerm_subnet_network_security_group_association` (×2)
- `azurerm_private_dns_zone` — `privatelink.blob.core.windows.net` and `privatelink.database.windows.net` (when `enable_private_endpoints=true`)
- `azurerm_private_dns_zone_virtual_network_link` (×2)

**Key outputs:** `vnet_id`, `public_subnet_name`, `private_subnet_name`, `private_subnet_id`, `public_nsg_association_id`, `private_nsg_association_id`, `blob_private_dns_zone_name`

---

### `modules/storage`

**Purpose:** ADLS Gen2 storage for Unity Catalog metastore and optionally a separate data lake.

**Resources created:**
- `azurerm_storage_account.metastore` — Standard, network-locked to private subnet, TLS 1.2, blob versioning, soft-delete
- `azurerm_storage_account.data` (count-gated on `create_separate_data_storage`) — ADLS Gen2 (`is_hns_enabled=true`)
- `azurerm_storage_container` — `metastore` and `data` containers in the metastore account
- `azurerm_private_endpoint` + `azurerm_private_dns_a_record` — for both storage accounts when private endpoints enabled
- `azurerm_storage_account_customer_managed_key` (count-gated on `enable_cmk`)

**Key outputs:** `metastore_storage_account_name`, `metastore_storage_account_id`

---

### `modules/cluster_policies`

**Purpose:** Governance guardrails for cluster creation — pins node types, Spark versions, autotermination limits, and init scripts.

**Policies created (each gated by a `create_*` bool variable):**

| Policy | Default nodes | Workers | Autotermination |
|---|---|---|---|
| Production | DS4_v2 | 4 (range 2–8) | 60 min (30–120) |
| Staging | DS3_v2 | 2 (range 1–4) | 30 min (15–60) |
| Development | DS3_v2 | 1 (range 0–4) | 20 min (10–60) |
| SQL Warehouse | DS4_v2 | 2 (range 1–6) | 30 min (10–60) |
| Interactive | DS3_v2 | 2 (range 1–4) | 30 min (15–60) |
| Job | DS4_v2 | 4 (fixed) | — |

All policies default to Spark 14.3.x-scala2.12.

---

## ABAC Module (`abac/`)

The ABAC directory is a **separate Terraform root** (own backend, own providers) that layers attribute-based access control on top of an already-provisioned workspace. Deploy it after the root module has fully applied.

### Provider aliasing

Two provider instances are required because Databricks separates account-level resources (groups) from workspace-level resources (grants, functions):

```hcl
provider "databricks" {
  alias         = "account"
  host          = "https://accounts.azuredatabricks.net"
  account_id    = var.databricks_account_id
  client_id     = var.databricks_account_client_id
  client_secret = var.databricks_account_client_secret
}

provider "databricks" {
  alias         = "workspace"
  host          = var.databricks_workspace_url
  client_id     = var.databricks_workspace_client_id
  client_secret = var.databricks_workspace_client_secret
}
```

All modules declare `providers = { databricks.account = databricks.account, databricks.workspace = databricks.workspace }` and each resource uses the correct alias.

### 5-step orchestration (`abac/main.tf`)

```
Step 1 — access_groups   (provider: account)
         Creates all groups in Databricks account console.
         ↓
Step 2 — catalog          (provider: workspace, for_each domain)
         Creates one catalog per domain: {env}_{domain}
         Creates schemas inside each catalog.
         Grants USE_CATALOG / USE_SCHEMA to structural groups.
         ↓
Step 3 — row_filters      (provider: workspace, for_each domain)
         Creates _policies schema.
         Deploys row-filter SQL functions per table archetype.
         Grants EXECUTE to reader groups.
         ↓
Step 4 — column_masks     (provider: workspace, for_each domain)
         Deploys col_mask_pii and col_mask_financial functions.
         Grants EXECUTE to reader + writer groups.
         ↓
Step 5 — table_grants     (provider: workspace, for_each domain)
         Grants SELECT (reader), SELECT+MODIFY (writer), ALL_PRIVILEGES (admin).
         Attaches row filter functions to tables via ALTER TABLE ... SET ROW FILTER.
         Attaches column mask functions per PII/financial column.
```

### Naming convention (`abac/locals.tf`)

All names are derived from a single pattern so renaming propagates everywhere:

| Object | Pattern | Example |
|---|---|---|
| Catalog | `{env}_{domain}` | `prd_finance` |
| Structural group | `{env}_{domain}_{role}` | `prd_finance_reader` |
| Region group | `{env}_{domain}_{table}_region_{value}` | `prd_finance_ledger_region_emea` |
| Entity group | `{env}_{domain}_{table}_{entity}` | `prd_finance_transactions_bu_retail` |
| Classification group | `{env}_{domain}_{table}_class_{value}` | `prd_risk_exposure_class_restricted` |
| PII access group | `{env}_{domain}_{table}_{access}` | `prd_finance_ledger_pii_clear` |
| Row filter fn | `row_filter_{table}_{archetype}` | `row_filter_ledger_region` |
| Column mask fn | `col_mask_pii_{domain}` | `col_mask_pii_finance` |

### Row filter archetypes

Each table declares one of four `row_filter_type` values:

| Archetype | Groups checked | Logic |
|---|---|---|
| `region_scoped` | `_region_{apac\|emea\|amer\|global}` | Row visible if user's region group matches the row's region column |
| `entity_scoped` | `_{bu_retail\|bu_wholesale\|bu_corporate\|all_entities}` | Row visible if user's entity group matches business unit |
| `classification` | `_class_{restricted\|confidential\|internal\|public}` | Hierarchical — restricted sees all, public sees only PUBLIC rows |
| `none` | — | No row filter applied |

All archetypes also exempt `dlt_pipeline_exempt`, `time_travel_exempt`, and domain admins unconditionally.

### Column mask behavior

| Group membership | PII columns | Financial columns |
|---|---|---|
| `dlt_pipeline_exempt` / `time_travel_exempt` / admin | Clear value | Clear value |
| `pii_clear_global` | Clear value | — |
| `pii_masked_global` | SHA-256 hash | — |
| Default (reader) | NULL | NULL |
| `financial_clear` | — | Clear value |
| `financial_masked` | — | Rounded to nearest 1000 |

---

## Environment Files

Environment-specific values live in `environments/{env}/{env}.tfvars`. Pass them with `-var-file` on every plan/apply.

### `environments/dev/dev.tfvars`
- `environment = "dev"`, 3 domains (`finance`, `risk`, `hr`), smaller table list for fast iteration.

### `environments/prd/prd.tfvars`
- `environment = "prd"`, 10+ domains, full table definitions including multi-table domains.
- Sensitive credentials (`client_id`, `client_secret`) are **not stored in the file** — pull from vault in CI/CD and pass as environment variables or `-var` flags.

---

## Two-Phase Apply (root module)

The Databricks provider cannot authenticate until the workspace ARM resource exists. Apply in two steps:

**Phase 1 — provision Azure infrastructure:**
```bash
terraform apply -target=azurerm_databricks_workspace.main \
                -target=module.networking \
                -target=module.storage \
                -var-file=environments/dev/dev.tfvars
```

**Phase 2 — configure Databricks (Unity Catalog, cluster policies):**
```bash
# Export the workspace resource ID from phase 1 output
export DATABRICKS_AZURE_RESOURCE_ID=$(terraform output -raw workspace_resource_id)
# Or set: DATABRICKS_HOST + DATABRICKS_TOKEN

terraform apply -var-file=environments/dev/dev.tfvars
```

**ABAC apply (after root is complete):**
```bash
cd abac/
terraform init -backend-config=backend-config.hcl
terraform apply -var-file=../environments/dev/dev.tfvars
```

---

## Quick Start

```bash
# 1. Bootstrap remote state (one-time per subscription)
bash scripts/01_setup_terraform_state.sh

# 2. Initialise root module
cd terraform/azure/
terraform init -backend-config=backend-config.hcl

# 3. Phase 1 — infrastructure only
terraform apply \
  -target=azurerm_databricks_workspace.main \
  -target=module.networking \
  -target=module.storage \
  -var-file=environments/dev/dev.tfvars

# 4. Phase 2 — full apply
export DATABRICKS_AZURE_RESOURCE_ID=$(terraform output -raw workspace_resource_id)
terraform apply -var-file=environments/dev/dev.tfvars

# 5. ABAC layer
cd abac/
terraform init -backend-config=backend-config.hcl
terraform apply -var-file=../environments/dev/dev.tfvars
```

---

## Adding a New Domain

1. Add the domain name to `domains` in the target `*.tfvars`.
2. Add its table definitions to `domain_tables` in the same file.
3. Run `terraform apply` on the ABAC root — modules use `for_each = var.domain_tables` so new keys automatically create a new catalog, schemas, filter functions, mask functions, and grants.
4. No module code changes needed.

---

## Key Design Decisions

**Separate ABAC root** — ABAC is deployed independently so it can be re-applied without touching Azure infrastructure. This lets the data governance team iterate on row filters and column masks without risking VNet or workspace changes.

**`for_each` on domain_tables** — Every ABAC module uses `for_each = var.domain_tables`, so adding a domain is a single-file change and Terraform computes the full diff automatically.

**`_policies` schema** — Row filter and column mask SQL functions live in a dedicated schema inside each catalog. This keeps policy objects isolated from business data and prevents accidental grants on data tables from exposing functions.

**`force = true` on groups** — Allows `terraform import` of groups that were created manually before Terraform adoption, without requiring a destroy/recreate cycle.

**Two Databricks providers** — Account-level resources (groups, metastore) require the account API (`accounts.azuredatabricks.net`); workspace-level resources (grants, functions, table policies) require the workspace API. Provider aliasing makes this explicit and prevents accidental resource creation against the wrong endpoint.
