# 05 — Quick Reference

## Terraform

### Core workflow

```bash
# Initialise (always pass backend-config)
terraform init -backend-config=../../backend-config.hcl

# Format
terraform fmt -recursive

# Validate
terraform validate

# Plan (save to file)
terraform plan -out=tfplan -var-file=environments/dev/dev.tfvars

# Apply from saved plan
terraform apply tfplan

# Apply directly (with auto-approve for CI)
terraform apply -auto-approve -var-file=environments/dev/dev.tfvars

# Destroy
terraform destroy -var-file=environments/dev/dev.tfvars
```

### Targeted operations

```bash
# Phase 1 — Azure infrastructure only
terraform apply \
  -target=azurerm_resource_group.main \
  -target=module.networking \
  -target=module.storage \
  -target=azurerm_databricks_workspace.main \
  -var-file=environments/dev/dev.tfvars

# Single module
terraform apply -target=module.cluster_policies -var-file=environments/dev/dev.tfvars

# Single resource
terraform apply -target=databricks_metastore.main -var-file=environments/dev/dev.tfvars
```

### State inspection

```bash
# List all managed resources
terraform state list

# Show a specific resource's state
terraform state show azurerm_databricks_workspace.main
terraform state show module.networking.azurerm_virtual_network.main

# Show all outputs
terraform output

# Get a single output (raw, for scripting)
terraform output -raw workspace_resource_id
terraform output -raw workspace_url

# Refresh state from live cloud
terraform refresh -var-file=environments/dev/dev.tfvars

# Import a resource created outside Terraform
terraform import azurerm_resource_group.main /subscriptions/{sub}/resourceGroups/{rg}
terraform import databricks_metastore.main <metastore-id>
```

### Debugging

```bash
# Verbose logging
TF_LOG=DEBUG terraform apply -var-file=environments/dev/dev.tfvars

# Dependency graph (requires graphviz)
terraform graph | dot -Tpng > graph.png

# Validate JSON
terraform validate -json | jq
```

---

## Azure CLI

### Authentication

```bash
# Login interactively
az login

# Login as service principal
az login --service-principal \
  --username $AZURE_CLIENT_ID \
  --password $AZURE_CLIENT_SECRET \
  --tenant $AZURE_TENANT_ID

# Set active subscription
az account set --subscription $AZURE_SUBSCRIPTION_ID

# Verify
az account show
```

### Resource groups

```bash
az group list --output table
az group show --name dev-databricks-rg
az group delete --name dev-databricks-rg --yes
```

### Networking

```bash
# List VNets
az network vnet list --resource-group dev-databricks-rg --output table

# Show subnets
az network vnet subnet list \
  --vnet-name dev-databricks-vnet \
  --resource-group dev-databricks-rg \
  --output table

# Verify subnet delegation
az network vnet subnet show \
  --vnet-name dev-databricks-vnet \
  --name public-subnet \
  --resource-group dev-databricks-rg \
  --query delegations

# Show NSG rules
az network nsg rule list \
  --nsg-name dev-databricks-nsg \
  --resource-group dev-databricks-rg \
  --output table

# List private endpoints
az network private-endpoint list \
  --resource-group dev-databricks-rg \
  --output table

# List private DNS zones
az network private-dns zone list \
  --resource-group dev-databricks-rg \
  --output table

# Test DNS resolution (from inside the VNet)
nslookup dbxmetastore.privatelink.blob.core.windows.net
```

### Storage

```bash
# List storage accounts
az storage account list --resource-group dev-databricks-rg --output table

# Show storage account details
az storage account show \
  --name <account-name> \
  --resource-group dev-databricks-rg

# Get access key
az storage account keys list \
  --account-name <account-name> \
  --resource-group dev-databricks-rg \
  --query '[0].value' -o tsv

# List containers
az storage container list --account-name <account-name> --account-key $ARM_ACCESS_KEY

# Check network rules
az storage account network-rule list \
  --account-name <account-name> \
  --resource-group dev-databricks-rg

# List state file versions
az storage blob list-versions \
  --container-name tfstate \
  --account-name <tfstate-account> \
  --account-key $ARM_ACCESS_KEY
```

### Service principals

```bash
# Create SP with role assignment
az ad sp create-for-rbac \
  --name databricks-terraform-sp \
  --role Contributor \
  --scopes /subscriptions/$AZURE_SUBSCRIPTION_ID

# Show SP details
az ad sp show --id <client-id>

# List role assignments for SP
az role assignment list --assignee <client-id> --output table

# Reset SP credentials
az ad sp credential reset --id <client-id>
```

### Databricks workspace (ARM)

```bash
# List workspaces
az databricks workspace list --resource-group dev-databricks-rg --output table

# Show workspace (includes workspace ID and URL)
az databricks workspace show \
  --name dev-databricks-workspace \
  --resource-group dev-databricks-rg

# Get workspace ARM resource ID
az databricks workspace show \
  --name dev-databricks-workspace \
  --resource-group dev-databricks-rg \
  --query id -o tsv
```

### Key Vault

```bash
# Create key vault
az keyvault create \
  --name databricks-kv \
  --resource-group dev-databricks-rg \
  --location eastus

# Store a secret
az keyvault secret set \
  --vault-name databricks-kv \
  --name client-secret \
  --value "<secret-value>"

# Read a secret
az keyvault secret show \
  --vault-name databricks-kv \
  --name client-secret \
  --query value -o tsv
```

---

## Databricks CLI

### Authentication

```bash
# Set via environment variables (recommended for CI/CD)
export DATABRICKS_HOST="https://adb-<id>.azuredatabricks.net"
export DATABRICKS_TOKEN="<pat-token>"

# Or configure interactively
databricks configure --token

# Test connection
databricks workspace ls /
```

### Clusters

```bash
databricks clusters list
databricks clusters get --cluster-id <id>
databricks clusters start --cluster-id <id>
databricks clusters delete --cluster-id <id>

# List cluster policies
databricks cluster-policies list
databricks cluster-policies get --policy-id <id>
```

### Jobs

```bash
databricks jobs list
databricks jobs get --job-id <id>
databricks jobs run-now --job-id <id>
databricks runs get --run-id <id>
databricks runs get-output --run-id <id>
databricks runs cancel --run-id <id>
```

### Unity Catalog

```bash
# Metastore
databricks metastores list
databricks metastores get --metastore-id <id>
databricks metastores assign --workspace-id <id> --metastore-id <id>

# Storage credentials
databricks storage-credentials list
databricks storage-credentials validate --credential-name <name>

# External locations
databricks external-locations list
databricks external-locations validate --name <name>

# Catalogs
databricks catalogs list
databricks schemas list --catalog-name <catalog>
databricks tables list --catalog-name <catalog> --schema-name <schema>
```

### Access control

```bash
# Groups
databricks groups list
databricks groups list-members --group-id <id>
databricks groups add-member --parent-id <group-id> --user-id <user-id>

# Permissions
databricks permissions get --object-type cluster --object-id <id>
databricks permissions update \
  --object-type cluster \
  --object-id <id> \
  --json '{"access_control_list": [{"group_name": "data-engineers", "permission_level": "CAN_RESTART"}]}'
```

---

## Databricks SDK (Python)

```python
from databricks.sdk import WorkspaceClient, AccountClient

# Workspace-level operations
w = WorkspaceClient(
    host="https://adb-<id>.azuredatabricks.net",
    token="<pat-token>"
)

# Account-level operations
a = AccountClient(
    host="https://accounts.azuredatabricks.net",
    account_id="<account-id>",
    client_id="<sp-client-id>",
    client_secret="<sp-secret>"
)

# List clusters
for c in w.clusters.list():
    print(c.cluster_id, c.cluster_name, c.state)

# List metastores
for m in a.metastores.list():
    print(m.metastore_id, m.name)

# List catalogs
for cat in w.catalogs.list():
    print(cat.name)

# List groups (account-level)
for g in a.groups.list():
    print(g.id, g.display_name)

# Check storage credential
cred = w.storage_credentials.get("<credential-name>")
print(cred.azure_service_principal.client_id)
```

---

## Environment Variables Reference

| Variable | Required | Purpose |
|---|---|---|
| `ARM_ACCESS_KEY` | Yes (Terraform) | Remote state storage account key |
| `DATABRICKS_AZURE_RESOURCE_ID` | Phase 2 | Workspace ARM ID for Databricks provider auth |
| `DATABRICKS_HOST` | CLI/SDK | Workspace URL (`https://adb-<id>.azuredatabricks.net`) |
| `DATABRICKS_TOKEN` | CLI/SDK | Personal access token |
| `AZURE_SUBSCRIPTION_ID` | Azure CLI | Target subscription |
| `AZURE_TENANT_ID` | Azure CLI | AAD tenant |
| `AZURE_CLIENT_ID` | Azure CLI SP login | SP client ID |
| `AZURE_CLIENT_SECRET` | Azure CLI SP login | SP client secret |
| `TF_VAR_azure_subscription_id` | Terraform | Passes to `var.azure_subscription_id` |
| `TF_VAR_azure_tenant_id` | Terraform | Passes to `var.azure_tenant_id` |
| `TF_VAR_azure_client_id` | Terraform | Passes to `var.azure_client_id` |
| `TF_VAR_azure_client_secret` | Terraform | Passes to `var.azure_client_secret` |
| `TF_LOG` | Optional | `INFO`, `DEBUG`, `TRACE`, `WARN`, `ERROR` |

---

## Post-Deployment Validation Script

```bash
#!/bin/bash
set -e

cd terraform/azure/

echo "=== Terraform outputs ==="
terraform output workspace_url
terraform output workspace_id

WORKSPACE_URL=$(terraform output -raw workspace_url)
WORKSPACE_RESOURCE_ID=$(terraform output -raw workspace_resource_id)

echo "=== Azure resources ==="
RG=$(terraform output -raw workspace_resource_id | cut -d'/' -f5)
az group show --name "$RG" --query name -o tsv
az databricks workspace show --ids "$WORKSPACE_RESOURCE_ID" --query workspaceUrl -o tsv

echo "=== Databricks Unity Catalog ==="
export DATABRICKS_HOST="https://$WORKSPACE_URL"
export DATABRICKS_AZURE_RESOURCE_ID="$WORKSPACE_RESOURCE_ID"
databricks metastores list
databricks storage-credentials list
databricks external-locations list

echo "=== Cluster policies ==="
databricks cluster-policies list

echo "=== Validation complete ==="
```
