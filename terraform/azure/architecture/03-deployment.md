# 03 — Deployment Guide

## Prerequisites

| Requirement | Details |
|---|---|
| Terraform | >= 1.5 |
| Azure CLI | >= 2.50 |
| Databricks CLI | >= 0.18 |
| Azure subscription | Contributor role for the Terraform service principal |
| Entra ID | Application Administrator role for the Terraform SP (to create app registrations) |
| Databricks account | Account-level admin access (for Unity Catalog metastore) |

---

## Step 1 — Bootstrap Remote State (one-time)

Run this once per Azure subscription before any Terraform deployment:

```bash
export AZURE_SUBSCRIPTION_ID="<your-subscription-id>"
bash terraform/azure/scripts/01_setup_terraform_state.sh
```

The script creates:
- A resource group for Terraform state
- A storage account with versioning, TLS 1.2, and firewall (default deny)
- A blob container named `tfstate`
- `terraform/backend-config.hcl` with the storage account details

Then export the storage account key:

```bash
export ARM_ACCESS_KEY="<key-from-script-output>"
```

---

## Step 2 — Configure Your Environment

Copy and edit the relevant `tfvars` file:

```bash
# Dev
cp terraform/azure/environments/dev/dev.tfvars terraform/azure/environments/dev/dev.tfvars.local
vi terraform/azure/environments/dev/dev.tfvars
```

Minimum required values (no defaults):

```hcl
azure_subscription_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
azure_tenant_id       = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
azure_client_id       = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
azure_client_secret   = "your-sp-client-secret"
environment           = "dev"
project_name          = "databricks"
```

Sensitive values (`azure_client_id`, `azure_client_secret`) must not be committed to Git. Pass them via environment variables in CI/CD:

```bash
export TF_VAR_azure_client_id="..."
export TF_VAR_azure_client_secret="..."
```

---

## Step 3 — Initialise Terraform

```bash
cd terraform/azure/
terraform init -backend-config=../../backend-config.hcl
```

---

## Step 4 — Phase 1 Apply (Azure Infrastructure)

The Databricks provider cannot authenticate until the workspace ARM resource exists. Apply Azure infrastructure first:

```bash
terraform apply \
  -target=azurerm_resource_group.main \
  -target=module.networking \
  -target=module.storage \
  -target=azurerm_databricks_workspace.main \
  -var-file=environments/dev/dev.tfvars
```

Wait for this to complete before proceeding. The workspace takes 5–15 minutes to provision.

---

## Step 5 — Phase 2 Apply (Databricks Configuration)

Export the workspace ARM resource ID from Phase 1 output, then run the full apply:

```bash
export DATABRICKS_AZURE_RESOURCE_ID=$(terraform output -raw workspace_resource_id)
terraform apply -var-file=environments/dev/dev.tfvars
```

This provisions:
- Unity Catalog metastore and workspace assignment
- Databricks storage credential and external locations
- Cluster policies

---

## Step 6 — Deploy ABAC Layer

After the root module is complete, deploy the ABAC layer:

```bash
cd abac/
terraform init -backend-config=backend-config.hcl
terraform apply -var-file=../environments/dev/dev.tfvars
```

The ABAC root requires additional variables not in the root tfvars:
- `databricks_account_id`
- `databricks_account_client_id` / `databricks_account_client_secret` (account-level SP)
- `databricks_workspace_url` (from `terraform output workspace_url` in root)
- `databricks_workspace_client_id` / `databricks_workspace_client_secret` (workspace-level SP)
- `domains` list and `domain_tables` map

---

## Validation Checklist

Run these checks after each phase:

**After Phase 1:**
- [ ] `terraform output workspace_url` returns a valid URL
- [ ] Workspace is visible in Azure portal
- [ ] Private endpoints created (if `enable_private_endpoints = true`)
- [ ] Storage account created and accessible from the private subnet
- [ ] VNet and subnets visible in Azure networking

**After Phase 2:**
- [ ] Databricks workspace URL is accessible
- [ ] Unity Catalog metastore visible in workspace Admin Console
- [ ] Storage credential validates (`databricks storage-credentials validate`)
- [ ] External locations validate (`databricks external-locations validate`)
- [ ] Cluster policies visible in workspace settings

**After ABAC:**
- [ ] Catalogs created per domain (`{env}_{domain}`)
- [ ] Groups created in Databricks account console
- [ ] Row filter and column mask functions exist in `{catalog}._policies`
- [ ] Test user can query a table and sees correct row/column filtering

---

## Troubleshooting

**`Error: could not authenticate to the Databricks workspace`**

Set `DATABRICKS_AZURE_RESOURCE_ID` before Phase 2 apply:
```bash
export DATABRICKS_AZURE_RESOURCE_ID=$(terraform output -raw workspace_resource_id)
```

**`Error: subnet must have Microsoft.Databricks/workspaces delegation`**

Both the public and private subnets must be delegated. This is handled by the networking module — do not manually remove the delegation.

**`Error: InvalidNSGAssociationId`**

The workspace `custom_parameters` require the NSG **association** resource ID, not the NSG ID. The networking module outputs `public_nsg_association_id` and `private_nsg_association_id` for this purpose.

**`Error: A resource with the ID already exists`**

A resource was created outside Terraform. Import it:
```bash
terraform import <resource_type>.<name> <azure-resource-id>
```

**Storage account network rule errors**

Network rules are configured inline in the `network_rules {}` block inside `azurerm_storage_account`. There is no separate `azurerm_storage_account_network_rule` resource.

**Metastore creation fails with `storage_root already in use`**

Another metastore is already using this storage container. Either use a different container name or import the existing metastore.

**Phase 2 fails with `metastore already exists in this region`**

Only one metastore per region per Databricks account is allowed on the E2 platform. Import the existing metastore:
```bash
terraform import databricks_metastore.main <metastore-id>
```

---

## Destroy Order

To tear down the full stack without state corruption:

```bash
# 1. Remove ABAC layer first
cd abac/
terraform destroy -var-file=../environments/dev/dev.tfvars

# 2. Remove root module
cd ..
terraform destroy -var-file=environments/dev/dev.tfvars
```

Do not destroy in reverse phase order (Phase 2 before Phase 1) — Databricks resources reference the workspace.
