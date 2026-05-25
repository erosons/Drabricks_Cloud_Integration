# Quick Reference Guide - Databricks Azure Implementation

**Fast lookup guide for common commands and configurations**

---

## 🚀 QUICK START (5 Minutes)

```bash
# 1. Clone and setup
git clone <repo-url>
cd databricks-azure-infrastructure
cp terraform/terraform.tfvars.example terraform/terraform.tfvars

# 2. Edit configuration
nano terraform/terraform.tfvars  # Add your Azure details

# 3. Deploy
cd terraform && terraform init
terraform plan && terraform apply

# 4. Configure workspace
export DATABRICKS_HOST=<workspace-url>
export DATABRICKS_TOKEN=<pat-token>

# 5. Validate
python -m pytest tests/ -v
```

---

## 🔧 TERRAFORM COMMANDS

### Initialization & Planning
```bash
# Initialize Terraform
terraform init

# Validate syntax
terraform validate

# Plan changes
terraform plan

# Plan with output
terraform plan -out=tfplan

# Show plan
terraform show tfplan
```

### Deployment
```bash
# Apply configuration
terraform apply tfplan

# Apply without plan
terraform apply -auto-approve

# Destroy resources
terraform destroy
terraform destroy -auto-approve
```

### State Management
```bash
# Show state
terraform show

# List resources
terraform state list

# Show specific resource
terraform state show azurerm_databricks_workspace.main

# Refresh state
terraform refresh

# Format code
terraform fmt -recursive
```

### Outputs
```bash
# Show all outputs
terraform output

# Show specific output
terraform output workspace_url

# JSON format
terraform output -json

# Raw value
terraform output -raw workspace_url
```

---

## ☁️ AZURE CLI COMMANDS

### Resource Groups
```bash
# Create resource group
az group create --name databricks-rg --location eastus

# List resource groups
az group list --output table

# Delete resource group
az group delete --name databricks-rg
```

### Virtual Networks
```bash
# Create VNet
az network vnet create \
  --name databricks-vnet \
  --resource-group databricks-rg \
  --address-prefix 10.0.0.0/16

# List VNets
az network vnet list --resource-group databricks-rg

# Create subnet
az network vnet subnet create \
  --vnet-name databricks-vnet \
  --name public-subnet \
  --address-prefix 10.0.0.0/24 \
  --resource-group databricks-rg
```

### Storage Accounts
```bash
# Create storage account
az storage account create \
  --name dbxmetastore \
  --resource-group databricks-rg \
  --location eastus \
  --sku Standard_LRS

# List storage accounts
az storage account list --resource-group databricks-rg

# Get storage keys
az storage account keys list \
  --account-name dbxmetastore \
  --resource-group databricks-rg

# Create container
az storage container create \
  --name metastore \
  --account-name dbxmetastore

# Upload file
az storage blob upload \
  --container-name metastore \
  --name file.txt \
  --file ./file.txt \
  --account-name dbxmetastore
```

### Service Principals
```bash
# Create service principal
az ad sp create-for-rbac \
  --name databricks-sp \
  --role "Storage Blob Data Contributor" \
  --scopes /subscriptions/{subscriptionId}/resourceGroups/databricks-rg/providers/Microsoft.Storage/storageAccounts/dbxmetastore

# List service principals
az ad sp list --filter "displayname eq 'databricks-sp'"

# Get service principal details
az ad sp show --id {service-principal-id}

# Assign role
az role assignment create \
  --assignee {service-principal-id} \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/{subscriptionId}
```

### Private Endpoints
```bash
# Create private endpoint
az network private-endpoint create \
  --name storage-pe \
  --resource-group databricks-rg \
  --vnet-name databricks-vnet \
  --subnet private-subnet \
  --private-connection-resource-id {storage-account-id} \
  --group-id blob \
  --connection-name storage-connection

# List private endpoints
az network private-endpoint list --resource-group databricks-rg

# Get private endpoint details
az network private-endpoint show \
  --name storage-pe \
  --resource-group databricks-rg
```

### Private DNS
```bash
# Create private DNS zone
az network private-dns zone create \
  --name privatelink.blob.core.windows.net \
  --resource-group databricks-rg

# List private DNS zones
az network private-dns zone list --resource-group databricks-rg

# Link zone to VNet
az network private-dns link vnet create \
  --name databricks-vnet-link \
  --zone-name privatelink.blob.core.windows.net \
  --virtual-network databricks-vnet \
  --resource-group databricks-rg

# Create A record
az network private-dns record-set a create \
  --name dbxmetastore \
  --zone-name privatelink.blob.core.windows.net \
  --resource-group databricks-rg

# Add A record
az network private-dns record-set a add-record \
  --ipv4-address 10.0.1.100 \
  --name dbxmetastore \
  --zone-name privatelink.blob.core.windows.net \
  --resource-group databricks-rg
```

### Databricks Workspaces
```bash
# List workspaces
az databricks workspace list --resource-group databricks-rg

# Show workspace details
az databricks workspace show \
  --name databricks-prod \
  --resource-group databricks-rg

# Update workspace
az databricks workspace update \
  --name databricks-prod \
  --resource-group databricks-rg \
  --tags environment=prod
```

---

## 🗄️ DATABRICKS CLI COMMANDS

### Configuration
```bash
# Set host and token
export DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
export DATABRICKS_TOKEN=your-pat-token

# Test connection
databricks workspace list /

# Configure CLI
databricks configure --token
```

### Clusters
```bash
# List clusters
databricks clusters list

# Get cluster details
databricks clusters get --cluster-id <cluster-id>

# Create cluster
databricks clusters create --json-file cluster.json

# Start cluster
databricks clusters start --cluster-id <cluster-id>

# Stop cluster
databricks clusters stop --cluster-id <cluster-id>

# Delete cluster
databricks clusters delete --cluster-id <cluster-id>

# List cluster policies
databricks cluster-policies list

# Get policy details
databricks cluster-policies get --policy-id <policy-id>
```

### Jobs
```bash
# List jobs
databricks jobs list

# Get job details
databricks jobs get --job-id <job-id>

# Create job
databricks jobs create --json-file job.json

# Run job
databricks jobs run-now --job-id <job-id>

# Cancel run
databricks runs cancel --run-id <run-id>

# Get run details
databricks runs get --run-id <run-id>
```

### Notebooks
```bash
# List notebooks
databricks workspace ls /

# Show notebook details
databricks workspace export /Users/user@example.com/notebook --format DBC

# Upload notebook
databricks workspace import --language PYTHON \
  --format SOURCE \
  --path /Users/user@example.com/notebook \
  ./local-notebook.py

# Delete notebook
databricks workspace delete --recursive /Users/user@example.com/notebook
```

### Metastore
```bash
# Create metastore
databricks metastores create \
  --name prod-metastore \
  --root-location abfss://metastore@storage.dfs.core.windows.net/

# List metastores
databricks metastores list

# Get metastore details
databricks metastores get --metastore-id <metastore-id>

# Assign metastore
databricks metastores assign \
  --workspace-id <workspace-id> \
  --metastore-id <metastore-id>
```

### Storage Credentials
```bash
# Create credential
databricks storage-credentials create \
  --name prod-storage-credential \
  --azure-service-principal \
  --tenant-id <tenant-id> \
  --client-id <client-id> \
  --client-secret <client-secret>

# List credentials
databricks storage-credentials list

# Get credential details
databricks storage-credentials get --credential-id <credential-id>

# Update credential
databricks storage-credentials update \
  --credential-id <credential-id> \
  --new-secret <new-secret>
```

### External Locations
```bash
# Create external location
databricks external-locations create \
  --name prod-data-location \
  --url abfss://data@storage.dfs.core.windows.net/prod \
  --credential-id <credential-id>

# List external locations
databricks external-locations list

# Get location details
databricks external-locations get --location-id <location-id>

# Update owner
databricks external-locations update \
  --location-id <location-id> \
  --owner <principal-id>
```

### Groups & Permissions
```bash
# Add group
databricks groups add-member \
  --parent-id <group-id> \
  --user-id <user-id>

# List group members
databricks groups list-members --group-id <group-id>

# Update permissions
databricks permissions update \
  --object-id <object-id> \
  --object-type workspace \
  --access-control group_name,permission_level
```

---

## 🐍 PYTHON SDK COMMANDS

### Basic Setup
```python
from databricks.sdk import WorkspaceClient

client = WorkspaceClient(
    host="https://your-workspace.cloud.databricks.com",
    token="your-pat-token"
)
```

### Clusters
```python
# List clusters
for cluster in client.clusters.list():
    print(f"{cluster.cluster_id}: {cluster.cluster_name}")

# Get cluster details
cluster = client.clusters.get(cluster_id="<cluster-id>")

# Create cluster
from databricks.sdk.service.compute import CreateCluster
cluster_config = CreateCluster(
    cluster_name="my-cluster",
    spark_version="13.3.x-scala2.12",
    node_type_id="Standard_DS4_v2",
    num_workers=2
)
response = client.clusters.create(cluster_config)
```

### Metastore
```python
# List metastores
for metastore in client.metastores.list():
    print(f"{metastore.metastore_id}: {metastore.name}")

# Get metastore details
metastore = client.metastores.get(metastore_id="<metastore-id>")

# Create metastore
metastore = client.metastores.create(
    name="prod-metastore",
    storage_root="abfss://metastore@storage.dfs.core.windows.net/"
)
```

### Storage Credentials
```python
# Create credential
credential = client.storage_credentials.create(
    name="prod-credential",
    azure_service_principal={
        "tenant_id": "<tenant-id>",
        "client_id": "<client-id>",
        "client_secret": "<client-secret>"
    }
)

# List credentials
for cred in client.storage_credentials.list():
    print(f"{cred.credential_id}: {cred.name}")
```

### Cluster Policies
```python
# Create policy
policy = client.cluster_policies.create(
    name="prod-policy",
    definition={
        "cluster_type": {"value": "all-purpose"},
        "num_workers": {"value": 2, "range": [1, 10]}
    }
)

# List policies
for policy in client.cluster_policies.list():
    print(f"{policy.policy_id}: {policy.name}")

# Assign permissions
client.cluster_policies.update_permissions(
    cluster_policy_id=policy.policy_id,
    access_control=[{
        "group_name": "data-engineers",
        "permission_level": "CAN_USE"
    }]
)
```

### Jobs
```python
# List jobs
for job in client.jobs.list():
    print(f"{job.job_id}: {job.settings.name}")

# Get job details
job = client.jobs.get(job_id=<job-id>)

# Run job
run = client.jobs.run_now(job_id=<job-id>)
print(f"Run ID: {run.run_id}")
```

---

## 📊 MONITORING COMMANDS

### Azure Monitor
```bash
# List metrics
az monitor metrics list-definitions \
  --resource /subscriptions/{subscriptionId}/resourceGroups/databricks-rg/providers/Microsoft.Databricks/workspaces/databricks-prod

# Get metric data
az monitor metrics list \
  --resource /subscriptions/{subscriptionId}/resourceGroups/databricks-rg/providers/Microsoft.Databricks/workspaces/databricks-prod \
  --metric "ClusterCount"

# Create alert rule
az monitor metrics alert create \
  --name cluster-cpu-alert \
  --resource-group databricks-rg \
  --window-size PT5M \
  --evaluation-frequency PT1M \
  --threshold 80 \
  --operator GreaterThan
```

### Logs
```bash
# View Databricks audit logs
databricks workspace ls /

# Check cluster logs
databricks clusters spark-submit \
  --cluster-id <cluster-id> \
  --jar-params "arg1" "arg2"
```

---

## 🔐 SECURITY COMMANDS

### Key Vault
```bash
# Create Key Vault
az keyvault create \
  --name databricks-kv \
  --resource-group databricks-rg

# Store secret
az keyvault secret set \
  --vault-name databricks-kv \
  --name databricks-token \
  --value <token-value>

# Retrieve secret
az keyvault secret show \
  --vault-name databricks-kv \
  --name databricks-token

# List secrets
az keyvault secret list --vault-name databricks-kv
```

### Firewall Rules
```bash
# Add firewall rule
az storage account network-rule add \
  --account-name dbxmetastore \
  --resource-group databricks-rg \
  --vnet-name databricks-vnet \
  --subnet-name private-subnet

# List firewall rules
az storage account network-rule list \
  --account-name dbxmetastore \
  --resource-group databricks-rg
```

---

## 🐛 DEBUGGING COMMANDS

### Network Diagnostics
```bash
# Test connectivity
az network watcher test-connectivity \
  --resource-group databricks-rg \
  --source-resource <source-vm-id> \
  --dest-address <dest-ip>

# Check NSG flow
az network watcher flow-log show \
  --nsg databricks-nsg \
  --resource-group databricks-rg

# DNS test
nslookup dbxmetastore.privatelink.blob.core.windows.net
```

### Databricks Logs
```bash
# Get workspace logs
databricks workspace get-status /

# Check cluster events
databricks clusters events \
  --cluster-id <cluster-id> \
  --start-time 1000000000 \
  --end-time 9999999999

# Get job run logs
databricks runs get-output --run-id <run-id>
```

### Terraform Debug
```bash
# Enable debug logging
TF_LOG=DEBUG terraform plan

# Verbose output
terraform apply -verbose

# Detailed error messages
terraform validate -json
```

---

## 📋 ENVIRONMENT VARIABLES

```bash
# Azure
export AZURE_SUBSCRIPTION_ID="your-subscription-id"
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"

# Databricks
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="your-pat-token"
export DATABRICKS_ORG_ID="your-org-id"

# Storage
export STORAGE_ACCOUNT="dbxmetastore"
export STORAGE_CONTAINER="metastore"

# Terraform
export TF_VAR_azure_subscription_id="your-subscription-id"
export TF_LOG=INFO  # Options: TRACE, DEBUG, INFO, WARN, ERROR
export TF_INPUT=false  # Disable interactive prompts
```

---

## ✅ VALIDATION CHECKLIST

```bash
# Verify Terraform
terraform validate
terraform plan -json | jq

# Verify Azure CLI
az account show
az group list --output table

# Verify Databricks CLI
databricks workspace ls /
databricks clusters list
databricks metastores list

# Verify Python SDK
python3 -c "from databricks.sdk import WorkspaceClient; print('SDK OK')"

# Verify Network
nslookup dbxmetastore.privatelink.blob.core.windows.net
curl -I https://your-workspace.cloud.databricks.com

# Run Tests
python -m pytest tests/ -v
```

---

## 🆘 TROUBLESHOOTING

### Cannot connect to workspace
```bash
# Check connection
databricks workspace ls /
# If fails: verify token and host

# Test URL
curl -I https://your-workspace.cloud.databricks.com
```

### Permission denied on storage
```bash
# Check role assignment
az role assignment list \
  --assignee <service-principal-id> \
  --scope /subscriptions/{subscriptionId}

# Assign role
az role assignment create \
  --assignee <service-principal-id> \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/{subscriptionId}/resourceGroups/databricks-rg/providers/Microsoft.Storage/storageAccounts/dbxmetastore
```

### Cluster fails to start
```bash
# Check cluster policy
databricks cluster-policies get --policy-id <policy-id>

# View cluster logs
databricks clusters spark-submit --cluster-id <cluster-id>

# Check Azure quotas
az compute vm list-usage --location eastus --output table
```

---

## 📚 DOCUMENTATION LINKS

| Resource | URL |
|----------|-----|
| Databricks Docs | https://docs.databricks.com |
| Azure CLI Docs | https://docs.microsoft.com/cli/azure |
| Terraform Docs | https://www.terraform.io/docs |
| Azure SDK (Python) | https://github.com/Azure/azure-sdk-for-python |
| Databricks SDK | https://databricks-sdk-py.readthedocs.io |

---

**Last Updated**: January 2026  
**Version**: 1.0  
**Status**: Production Ready
