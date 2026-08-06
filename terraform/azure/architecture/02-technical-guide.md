# 02 — Technical Guide

## Networking Module (`modules/networking`)

### What it provisions

| Resource | Details |
|---|---|
| `azurerm_virtual_network` | Named `{env}-{project}-vnet`, address space from `var.vnet_address_space` |
| `azurerm_subnet.public` | Public Databricks subnet — delegated to `Microsoft.Databricks/workspaces`; service endpoints: Storage, KeyVault, SQL |
| `azurerm_subnet.private` | Private Databricks subnet — **also** delegated to `Microsoft.Databricks/workspaces` (required for VNet injection) |
| `azurerm_network_security_group` | 3 rules: allow VNet inbound, allow AzureCloud outbound, allow HTTPS outbound |
| `azurerm_subnet_network_security_group_association` ×2 | Binds NSG to both subnets |
| `azurerm_private_dns_zone` | `privatelink.blob.core.windows.net` + `privatelink.database.windows.net` (when `enable_private_endpoints = true`) |
| `azurerm_private_dns_zone_virtual_network_link` ×2 | Links DNS zones to the VNet |

### Key design notes

Both subnets must have the Databricks delegation. Without it on the private subnet, workspace creation fails with a subnet delegation error. Do not add `tags` to subnet resources — the provider rejects them.

The `azurerm_databricks_workspace` resource requires the NSG **association** resource IDs (not the NSG's own ARM ID) in `custom_parameters`. The networking module exports `public_nsg_association_id` and `private_nsg_association_id` for this purpose.

### Outputs

| Output | Type | Used by |
|---|---|---|
| `vnet_id` | string | workspace `custom_parameters.virtual_network_id` |
| `public_subnet_name` | string | workspace `custom_parameters.subnet_name_public` |
| `private_subnet_name` | string | workspace `custom_parameters.subnet_name_private` |
| `private_subnet_id` | string | storage module `allowed_subnet_ids`, `private_subnet_id` |
| `public_nsg_association_id` | string | workspace `custom_parameters.public_subnet_network_security_group_association_id` |
| `private_nsg_association_id` | string | workspace `custom_parameters.private_subnet_network_security_group_association_id` |
| `blob_private_dns_zone_name` | string | storage module `blob_private_dns_zone_name` (zone name, not ARM ID) |

---

## Storage Module (`modules/storage`)

### What it provisions

| Resource | Details |
|---|---|
| `azurerm_storage_account.metastore` | Standard LRS/GRS, `is_hns_enabled = true` (ADLS Gen2), `enable_https_traffic_only = true`, TLS 1.2, network rules default-deny, restricted to `var.allowed_subnet_ids` |
| `azurerm_storage_account.data` | Count-gated on `var.create_separate_data_storage`; same security settings as metastore account |
| `azurerm_storage_container` | `metastore` and `data` containers in the metastore account |
| `azurerm_private_endpoint` + `azurerm_private_dns_a_record` | For both accounts when `enable_private_endpoints = true` |
| `azurerm_storage_account_customer_managed_key` | Count-gated on `var.enable_cmk`; requires `key_vault_id`, `key_vault_key_name`, `user_assigned_identity_id` |

### Network rule implementation note

Network rules are implemented via the inline `network_rules {}` block inside `azurerm_storage_account`, not via a separate resource. `azurerm_storage_account_network_rule` does not exist in the azurerm provider.

### DNS zone name vs ARM ID

The storage module takes `blob_private_dns_zone_name` as a **string name** (e.g., `privatelink.blob.core.windows.net`), not an ARM resource ID. The networking module's `blob_private_dns_zone_name` output returns the `.name` attribute, not `.id`.

### Outputs

| Output | Used by |
|---|---|
| `metastore_storage_account_name` | `databricks_metastore.storage_root` URL, root `outputs.tf` |
| `metastore_storage_account_id` | `azurerm_role_assignment.scope`, root `outputs.tf` |
| `data_storage_account_id` | Root outputs (optional) |
| `data_storage_account_name` | Root outputs (optional) |
| `metastore_container_name` | Root outputs (optional) |

---

## Cluster Policies Module (`modules/cluster_policies`)

### Policies created

Each policy is gated by a `create_*` bool variable.

| Policy | Node type | Workers | Autotermination |
|---|---|---|---|
| Production | DS4_v2 | 4 (range 2–8) | 60 min (30–120) |
| Staging | DS3_v2 | 2 (range 1–4) | 30 min (15–60) |
| Development | DS3_v2 | 1 (range 0–4) | 20 min (10–60) |
| SQL Warehouse | DS4_v2 | 2 (range 1–6) | 30 min (10–60) |
| Interactive | DS3_v2 | 2 (range 1–4) | 30 min (15–60) |
| Job | DS4_v2 | 4 (fixed) | — |

All policies default to Spark 14.3.x-scala2.12.

### Policy JSON schema

Databricks cluster policy JSON uses `type`, `defaultValue`, `minValue`, `maxValue`, and `values` keys. The incorrect `range` key is not valid:

```hcl
# CORRECT
num_workers = jsonencode({
  type         = "range"
  defaultValue = var.prod_num_workers
  minValue     = var.prod_worker_range[0]
  maxValue     = var.prod_worker_range[1]
})

# CORRECT — allowlist
node_type_id = jsonencode({
  type         = "allowlist"
  values       = var.prod_allowed_worker_types
  defaultValue = var.prod_worker_node_type
})
```

---

## Unity Catalog Setup

### Metastore

The metastore is backed by an ADLS Gen2 container:

```hcl
resource "databricks_metastore" "main" {
  name         = "${var.environment}-metastore"
  storage_root = "abfss://${var.metastore_container_name}@${module.storage.metastore_storage_account_name}.dfs.core.windows.net/"
  region       = var.location
}
```

After creation, it is attached to the workspace:

```hcl
resource "databricks_metastore_assignment" "workspace" {
  workspace_id         = azurerm_databricks_workspace.main.workspace_id
  metastore_id         = databricks_metastore.main.metastore_id
  default_catalog_name = var.default_catalog_name
}
```

### Storage credential

Databricks authenticates to ADLS via a service principal storage credential:

```hcl
resource "databricks_storage_credential" "service_principal" {
  azure_service_principal {
    directory_id   = var.azure_tenant_id
    application_id = azuread_application.databricks_sp.client_id
    client_secret  = azuread_service_principal_password.databricks_sp.value
  }
}
```

The SP is granted `Storage Blob Data Contributor` on the metastore storage account via `azurerm_role_assignment`.

### External locations

Two external locations reference the metastore and data containers. Both use the SP storage credential:

```hcl
resource "databricks_external_location" "metastore" {
  url           = "abfss://${var.metastore_container_name}@${module.storage.metastore_storage_account_name}.dfs.core.windows.net/"
  credential_id = databricks_storage_credential.service_principal.id
}
```

---

## ABAC Module (`abac/`)

The ABAC directory is a **separate Terraform root** (own `terraform.tfstate`, own providers). Deploy it after the root module has fully applied.

### Provider configuration

Two provider aliases are required — account-level resources (groups) and workspace-level resources (grants, functions) use different API endpoints:

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

All modules pass `providers = { databricks.account = databricks.account, databricks.workspace = databricks.workspace }`.

### 5-step orchestration

```
Step 1 — access_groups   (account provider)
         Creates all groups in Databricks account console.
         ↓
Step 2 — catalog          (workspace provider, for_each domain)
         Creates {env}_{domain} catalog + schemas.
         Grants USE_CATALOG / USE_SCHEMA to structural groups.
         ↓
Step 3 — row_filters      (workspace provider, for_each domain)
         Creates _policies schema.
         Deploys row-filter SQL functions.
         Grants EXECUTE to reader groups.
         ↓
Step 4 — column_masks     (workspace provider, for_each domain)
         Deploys col_mask_pii and col_mask_financial functions.
         Grants EXECUTE to reader + writer groups.
         ↓
Step 5 — table_grants     (workspace provider, for_each domain)
         Grants SELECT (reader), SELECT+MODIFY (writer), ALL_PRIVILEGES (admin).
         Attaches row filter and column mask functions via ALTER TABLE.
```

### Naming convention

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

| Archetype | Groups checked | Logic |
|---|---|---|
| `region_scoped` | `_region_{apac\|emea\|amer\|global}` | Row visible if user's region group matches the row's region column |
| `entity_scoped` | `_{bu_retail\|bu_wholesale\|bu_corporate\|all_entities}` | Row visible if user's entity group matches business unit |
| `classification` | `_class_{restricted\|confidential\|internal\|public}` | Hierarchical: restricted sees all, public sees only PUBLIC rows |
| `none` | — | No row filter applied |

`dlt_pipeline_exempt`, `time_travel_exempt`, and domain admins are unconditionally exempted in all archetypes.

### Column mask behavior

| Group membership | PII columns | Financial columns |
|---|---|---|
| `dlt_pipeline_exempt` / `time_travel_exempt` / admin | Clear value | Clear value |
| `pii_clear_global` | Clear value | — |
| `pii_masked_global` | SHA-256 hash | — |
| Default (reader) | NULL | NULL |
| `financial_clear` | — | Clear value |
| `financial_masked` | — | Rounded to nearest 1000 |

### Adding a new domain

1. Add the domain name to `domains` in `{env}.tfvars`.
2. Add its table definitions to `domain_tables` in the same file.
3. Run `terraform apply` on the ABAC root.

No module code changes are needed — all ABAC modules use `for_each = var.domain_tables`.
