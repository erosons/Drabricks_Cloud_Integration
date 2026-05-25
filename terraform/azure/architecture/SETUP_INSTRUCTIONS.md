# Databricks Azure Infrastructure Setup Instructions

## Quick Start Guide

This package contains everything you need to deploy Databricks on Azure with enterprise-grade networking, metastore, and governance.

### Contents

1. **Databricks_Azure_Infrastructure_Implementation_Guide.md** - Comprehensive implementation guide
2. **Repository Template** - Complete directory structure with templates
3. **Configuration Examples** - Terraform, CLI, and Python examples

### Step 1: Create GitHub Repository

```bash
# Initialize your own repository
git init databricks-azure-infrastructure
cd databricks-azure-infrastructure

# Copy the template files to your repository
# See structure below
```

### Step 2: Create Directory Structure

```bash
mkdir -p {terraform,databricks-cli,python-sdk,documentation,tests,monitoring,scripts,.github/workflows}
mkdir -p databricks-cli/{cluster-policies,scripts,notebooks}
mkdir -p python-sdk
mkdir -p documentation
mkdir -p monitoring/{terraform,dashboards,alerts}
```

### Step 3: Terraform Configuration

Create `terraform/variables.tf`:
```hcl
variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "azure_resource_group" {
  description = "Azure resource group name"
  type        = string
  default     = "databricks-rg"
}

variable "azure_location" {
  description = "Azure region"
  type        = string
  default     = "eastus"
}

variable "databricks_workspace_name" {
  description = "Databricks workspace name"
  type        = string
  default     = "databricks-prod"
}
```

Create `terraform/terraform.tfvars`:
```hcl
azure_subscription_id   = "YOUR_SUBSCRIPTION_ID"
azure_resource_group    = "databricks-rg"
azure_location          = "eastus"
databricks_workspace_name = "databricks-prod"
```

### Step 4: Initialize and Deploy

```bash
# Initialize Terraform
cd terraform
terraform init

# Plan deployment
terraform plan -out=tfplan

# Apply configuration
terraform apply tfplan
```

### Step 5: Configure Databricks

```bash
# Set environment variables
export DATABRICKS_HOST="https://YOUR_WORKSPACE_URL"
export DATABRICKS_TOKEN="YOUR_PAT_TOKEN"

# Create metastore
cd ../databricks-cli
./scripts/create-metastore.sh

# Setup storage credentials
./scripts/create-storage-credentials.sh

# Create external locations
./scripts/create-external-locations.sh

# Setup cluster policies
./scripts/setup-cluster-policies.sh
```

### Step 6: Validation

```bash
# Run tests
cd ../
python -m pip install -r python-sdk/requirements.txt
python -m pytest tests/ -v
```

## Key Files to Configure

### 1. Terraform Variables (terraform/terraform.tfvars)
- Azure subscription ID
- Resource group name
- Location
- Workspace name
- Storage account names
- VNet address spaces

### 2. Environment Variables (.env)
```bash
AZURE_SUBSCRIPTION_ID=your-subscription-id
AZURE_TENANT_ID=your-tenant-id
AZURE_RESOURCE_GROUP=databricks-rg
AZURE_LOCATION=eastus

DATABRICKS_HOST=https://your-workspace.cloud.databricks.com
DATABRICKS_TOKEN=your-pat-token

STORAGE_ACCOUNT=dbxmetastore
METASTORE_CONTAINER=metastore

AZURE_CLIENT_ID=service-principal-id
AZURE_CLIENT_SECRET=service-principal-secret
```

### 3. Service Principal Setup
```bash
# Create service principal
az ad sp create-for-rbac \
  --name databricks-sp \
  --role "Storage Blob Data Contributor" \
  --scopes /subscriptions/{subscriptionId}/resourceGroups/databricks-rg/providers/Microsoft.Storage/storageAccounts/dbxmetastore
```

## Implementation Timeline

| Phase | Activities | Duration |
|-------|-----------|----------|
| Network Setup | VNet, Subnets, Private Endpoints | 1-2 days |
| Storage | Storage accounts, containers | 1 day |
| Workspace | Databricks workspace with VNet injection | 1-2 days |
| Metastore | Unity Catalog setup | 1 day |
| Governance | Policies, groups, monitoring | 1-2 days |
| **Total** | | **5-7 days** |

## Deployment Validation Checklist

- [ ] Azure CLI authenticated
- [ ] Terraform initialized
- [ ] Resource group created
- [ ] VNet and subnets provisioned
- [ ] Private Endpoints configured
- [ ] Storage accounts created
- [ ] Service Principal created and assigned roles
- [ ] Databricks workspace deployed
- [ ] Unity Catalog metastore created
- [ ] Storage credentials configured
- [ ] External locations created
- [ ] Cluster policies applied
- [ ] Groups and permissions configured
- [ ] Monitoring and alerts enabled
- [ ] Test suite passed

## Important Notes

### Security
- Never commit secrets or credentials to Git
- Use environment variables or Azure Key Vault
- Always use Private Endpoints for Azure services
- Rotate service principal secrets regularly

### Cost Management
- Set autotermination to 30 minutes
- Use spot instances for non-production
- Right-size clusters for your workloads
- Monitor costs via Databricks cost analysis

### Governance
- Use Unity Catalog for all new workspaces
- Implement cluster policies for all environments
- Separate prod/staging/dev environments
- Enable audit logging

## Troubleshooting

### Cannot reach Private Endpoint
- Check private DNS zone configuration
- Verify NSG rules allow traffic
- Ensure VNet peering is configured (if applicable)

### Storage access denied
- Verify service principal has "Storage Blob Data Contributor" role
- Check storage account firewall rules
- Ensure storage credential is properly configured

### Cluster startup fails
- Check Azure VM quotas for node types
- Verify cluster policies don't conflict
- Check network security groups

## Next Steps

1. **Review Documentation**: Read the comprehensive implementation guide
2. **Customize for Your Organization**: Update variables and policies
3. **Test in Dev Environment**: Validate with non-production resources
4. **Deploy to Production**: Follow deployment instructions
5. **Monitor and Maintain**: Set up alerts and regular reviews

## Support & Resources

- [Databricks Azure Documentation](https://docs.databricks.com)
- [Azure Private Link Documentation](https://docs.microsoft.com/azure/private-link/)
- [Unity Catalog Guide](https://docs.databricks.com/data-governance/unity-catalog/)
- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/)

---

**Version**: 1.0  
**Last Updated**: January 2026  
**Status**: Production Ready
