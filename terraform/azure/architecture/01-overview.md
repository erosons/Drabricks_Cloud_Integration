# 01 — Architecture Overview

## Platform Layers

```
┌─────────────────────────────────────────────────────────────┐
│                    ABAC / Data Governance                    │
│   access_groups → catalog → row_filters → column_masks      │
│                        → table_grants                        │
├─────────────────────────────────────────────────────────────┤
│                    Databricks Platform                       │
│   Unity Catalog metastore · storage credentials             │
│   external locations · cluster policies                     │
├─────────────────────────────────────────────────────────────┤
│                    Azure Infrastructure                      │
│   VNet · subnets · NSG · private DNS zones                  │
│   ADLS Gen2 storage · private endpoints                     │
│   Entra ID service principal · RBAC assignments             │
└─────────────────────────────────────────────────────────────┘
```

The platform is deployed in two Terraform roots:

1. **Root module** (`terraform/azure/`) — provisions all Azure and Databricks platform resources in one apply (two phases required; see [03-deployment.md](03-deployment.md)).
2. **ABAC module** (`terraform/azure/abac/`) — provisions attribute-based access control on top of an already-running workspace. Deploy after the root module.

---

## Root Module Resources

| Resource | What it creates |
|---|---|
| `azurerm_resource_group.main` | Resource container: `{env}-{project}-rg` |
| `module.networking` | VNet, subnets, NSG, private DNS zones |
| `module.storage` | ADLS Gen2 metastore account, optional data lake account, containers, private endpoints |
| `azurerm_databricks_workspace.main` | Premium workspace injected into the VNet |
| `azuread_application` + `azuread_service_principal` | Entra ID SP for ADLS authentication |
| `azurerm_role_assignment` | Storage Blob Data Contributor on metastore account |
| `module.cluster_policies` | 6 cluster policies (prod, staging, dev, SQL, interactive, job) |
| `databricks_metastore` | Unity Catalog metastore backed by ADLS |
| `databricks_metastore_assignment` | Attaches metastore to workspace |
| `databricks_storage_credential` | Credential using the SP client secret |
| `databricks_external_location` ×2 | External locations for metastore and data containers |

---

## Security Design

**Network isolation**
- Databricks workspace deployed with VNet injection — both public and private subnets are delegated to `Microsoft.Databricks/workspaces`
- NSG restricts inbound to VNet only, outbound to Azure backbone and HTTPS only
- Private endpoints for ADLS Gen2 (when `enable_private_endpoints = true`), backed by private DNS zones
- Storage accounts deny public network access by default

**Identity and access**
- Entra ID service principal (not a user account) for Databricks ↔ ADLS authentication
- SP has Storage Blob Data Contributor only on the metastore account — no broader permissions
- SP password rotated by re-applying (lifecycle `ignore_changes = [end_date]` prevents drift detection loops)
- Sensitive outputs (`service_principal_client_id`, `service_principal_client_secret`) marked sensitive in Terraform

**Data governance (ABAC layer)**
- Row-level security via Unity Catalog row filter functions — four archetypes: region, entity, classification, none
- Column masking via Unity Catalog column mask functions — PII columns masked to SHA-256 hash or NULL; financial columns rounded or NULL
- Policy objects isolated in `_policies` schema per catalog — cannot be accidentally exposed by broad data grants

---

## Cost Estimates (Azure East US)

| Component | Dev / month | Production / month |
|---|---|---|
| Databricks Premium workspace | ~$200 | ~$400 |
| Databricks clusters (DBU) | ~$300–500 | ~$2,000–4,000 |
| ADLS Gen2 storage | ~$20–50 | ~$200–500 |
| Private endpoints (×2) | ~$15 | ~$15 |
| VNet / NSG | ~$5 | ~$5 |
| **Total estimate** | **~$540–770** | **~$2,600–5,000** |

Costs vary significantly with cluster uptime and data volume. Autotermination policies (10–120 min depending on policy) are the primary cost control lever.

---

## Pre-Deployment Checklist

Before running `terraform apply`:

- [ ] Azure subscription ID and tenant ID on hand
- [ ] Terraform service principal created with Contributor on the target resource group (or subscription) + Application Administrator in Entra ID
- [ ] Remote state storage account bootstrapped (`scripts/01_setup_terraform_state.sh`)
- [ ] `ARM_ACCESS_KEY` environment variable set to the storage account key
- [ ] `environments/{env}/{env}.tfvars` reviewed and customised for your environment
- [ ] Databricks account-level admin access available (needed for Unity Catalog metastore operations)
- [ ] Phase 1 apply completes successfully before running Phase 2

---

## Module Dependency Graph

```
networking ──► storage ──────────────────────────────► metastore
           └──► workspace ──► cluster_policies          │
                          └──────────────────────────► metastore_assignment
                                                        │
                                                        storage_credential
                                                        │
                                                        external_location (×2)
```

For the ABAC layer:

```
access_groups ──► catalog ──► row_filters ──► column_masks ──► table_grants
```
