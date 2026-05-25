# Databricks Platform Infrastructure on Azure

**Enterprise-Grade Implementation Guide with Networking, Metastore, Storage Credentials & Cluster Policies**

## Overview

This comprehensive infrastructure-as-code solution provides a complete implementation of Databricks on Microsoft Azure with:

- ✅ **Secure Networking**: Private Endpoints, Private Links, VNet injection
- ✅ **Centralized Metadata**: Unity Catalog with metastore
- ✅ **Access Control**: Service Principal-based storage credentials
- ✅ **Governance**: Cluster policies and RBAC
- ✅ **Applications**: Databricks Apps with network integration
- ✅ **Infrastructure as Code**: Terraform for reproducible deployments
- ✅ **Automation**: Python SDK and Databricks CLI scripts
- ✅ **Monitoring**: Azure Monitor integration and dashboards

## Quick Start

### Prerequisites
```bash
# Required tools
- Azure CLI (authenticated)
- Terraform >= 1.5
- Databricks CLI
- Python 3.9+
- Git
```

### 5-Minute Setup
```bash
# 1. Clone repository
git clone https://github.com/your-org/databricks-azure-infrastructure
cd databricks-azure-infrastructure

# 2. Configure variables
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# Edit terraform.tfvars with your Azure details

# 3. Deploy infrastructure
cd terraform
terraform init
terraform plan
terraform apply

# 4. Configure workspace
cd ../databricks-cli
export DATABRICKS_HOST=$(cat ../deployment-outputs.json | jq -r '.workspace_url.value')
export DATABRICKS_TOKEN=$YOUR_PAT_TOKEN
./scripts/create-metastore.sh

# 5. Validate
cd ../
python -m pytest tests/ -v
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Databricks Workspace                      │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Apps | Notebooks | SQL | Jobs | Clusters          │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
    Private        Unity Catalog   Storage
    Endpoints      Metastore       Credentials
        │              │              │
        └──────────────┼──────────────┘
                       │
        ┌──────────────┼──────────────┐
        │              │              │
        ▼              ▼              ▼
   Azure VNet   Workspace MSI   Azure Storage
   with NSG    Service Principal Private Endpoints
```

## Directory Structure

```
databricks-azure-infrastructure/
├── README.md                          # This file
├── IMPLEMENTATION_GUIDE.md            # Detailed guide
├── .github/
│   └── workflows/                     # CI/CD pipelines
│       ├── deploy-infrastructure.yml
│       └── validate-terraform.yml
├── terraform/                         # Infrastructure as Code
│   ├── main.tf                        # Main configuration
│   ├── variables.tf                   # Variable definitions
│   ├── outputs.tf                     # Output definitions
│   ├── networking.tf                  # VNet & networking
│   ├── storage.tf                     # Storage accounts
│   ├── databricks.tf                  # Workspace config
│   ├── terraform.tfvars.example       # Variable template
│   └── backend.tf                     # Remote state config
├── databricks-cli/
│   ├── cluster-policies/
│   │   ├── prod-policy.json          # Production policy
│   │   ├── staging-policy.json       # Staging policy
│   │   └── dev-policy.json           # Development policy
│   ├── scripts/
│   │   ├── create-metastore.sh       # Metastore setup
│   │   ├── create-storage-credentials.sh
│   │   ├── create-external-locations.sh
│   │   ├── setup-groups-and-permissions.sh
│   │   └── deploy-clusters.sh
│   └── notebooks/
│       ├── setup-workspace.py        # Workspace initialization
│       └── validation-tests.py       # Validation tests
├── python-sdk/
│   ├── requirements.txt              # Python dependencies
│   ├── config.py                     # Configuration management
│   ├── metastore_manager.py          # Metastore automation
│   ├── cluster_manager.py            # Cluster automation
│   ├── storage_manager.py            # Storage automation
│   └── main.py                       # Main orchestrator
├── documentation/
│   ├── architecture.md               # Detailed architecture
│   ├── networking-guide.md           # Network setup guide
│   ├── metastore-guide.md            # Metastore configuration
│   ├── storage-credentials-guide.md  # Storage credential setup
│   ├── cluster-policies-guide.md     # Cluster policy guide
│   └── troubleshooting.md            # Troubleshooting guide
├── tests/
│   ├── test_infrastructure.py        # Infrastructure tests
│   ├── test_connectivity.py          # Connectivity tests
│   ├── test_storage_access.py        # Storage access tests
│   └── test_cluster_policies.py      # Policy validation tests
├── monitoring/
│   ├── terraform/
│   │   └── monitoring.tf             # Monitor setup
│   ├── dashboards/
│   │   └── databricks-metrics.json   # Dashboard config
│   └── alerts/
│       └── alert-rules.tf            # Alert rules
└── scripts/
    ├── deploy-all.sh                 # Full deployment script
    ├── validate-setup.sh             # Validation script
    ├── cleanup.sh                    # Cleanup script
    └── backup-config.sh              # Backup script
```

## Key Components

### 1. Networking with Private Endpoints
- VNet with custom address space (10.0.0.0/16)
- Public and Private subnets
- Network Security Groups with restricted rules
- Private Endpoints for Databricks, Storage, Key Vault
- Private DNS Zones for name resolution

### 2. Metastore & Unity Catalog
- Centralized metadata storage
- Azure Storage-backed metastore
- Unity Catalog for governance
- External Locations for data access
- RBAC-based access control

### 3. Storage Credentials
- Service Principal authentication
- Managed Identity support
- Secure secret rotation
- Storage Blob Data Contributor role
- External location bindings

### 4. Cluster Policies
- Production cluster policies (2-10 workers, Standard_DS4_v2)
- Staging cluster policies (1-5 workers, Standard_DS3_v2)
- Development cluster policies (1-3 workers, Standard_DS2_v2)
- Autotermination enforcement (15-120 min range)
- Node type restrictions

### 5. Databricks Apps Integration
- Workspace-level app configuration
- Secure networking for applications
- Private Endpoint support
- Custom routing and DNS

## Deployment Timeline

| Phase | Activities | Duration | Owner |
|-------|-----------|----------|-------|
| **1. Planning** | Architecture review, access requests | 2-3 days | Infrastructure Team |
| **2. Network** | VNet, subnets, Private Endpoints | 1-2 days | Network Team |
| **3. Storage** | Storage accounts, firewall rules | 1 day | Storage Team |
| **4. Workspace** | Databricks deployment, VNet injection | 1-2 days | Databricks Team |
| **5. Metastore** | Unity Catalog, credentials, locations | 1 day | Data Team |
| **6. Governance** | Policies, groups, permissions | 1-2 days | Security Team |
| **7. Testing** | Validation, troubleshooting | 1 day | QA Team |
| **8. Production** | Monitor, document, handoff | Ongoing | Operations |

**Total: 8-12 Business Days**

## Configuration Guide

### Step 1: Azure Setup
```bash
# Create resource group
az group create --name databricks-rg --location eastus

# Create storage accounts
az storage account create \
  --name dbxmetastore \
  --resource-group databricks-rg \
  --location eastus

# Create service principal
az ad sp create-for-rbac \
  --name databricks-sp \
  --role "Storage Blob Data Contributor"
```

### Step 2: Terraform Deployment
```bash
cd terraform

# Initialize
terraform init

# Review plan
terraform plan -out=tfplan

# Apply configuration
terraform apply tfplan

# Save outputs
terraform output -json > ../deployment-outputs.json
```

### Step 3: Databricks Configuration
```bash
cd ../databricks-cli

# Set environment variables
export DATABRICKS_HOST=$(cat ../deployment-outputs.json | jq -r '.workspace_url.value')
export DATABRICKS_TOKEN=$YOUR_PAT_TOKEN

# Run setup scripts
./scripts/create-metastore.sh
./scripts/create-storage-credentials.sh
./scripts/create-external-locations.sh
./scripts/setup-groups-and-permissions.sh
```

### Step 4: Validation
```bash
cd ../

# Run test suite
python -m pip install -r python-sdk/requirements.txt
python -m pytest tests/ -v

# Manual validation
./scripts/validate-setup.sh
```

## Best Practices

### Security
- ✓ Always use Private Endpoints for Azure services
- ✓ Rotate service principal secrets every 90 days
- ✓ Implement least privilege RBAC
- ✓ Enable encryption in transit and at rest
- ✓ Use Azure Key Vault for secret management
- ✓ Monitor all changes via audit logs

### Governance
- ✓ Implement Unity Catalog for all workspaces
- ✓ Use Cluster Policies for all environments
- ✓ Separate prod/staging/dev resources
- ✓ Enable comprehensive logging
- ✓ Regular compliance audits

### Cost Management
- ✓ Set autotermination to 30 minutes
- ✓ Use spot instances for non-production
- ✓ Right-size clusters based on workloads
- ✓ Monitor costs via Databricks analytics
- ✓ Implement resource quotas

### Operational Excellence
- ✓ Use Infrastructure as Code for all deployments
- ✓ Version control all configurations
- ✓ Implement CI/CD pipelines
- ✓ Regular disaster recovery tests
- ✓ Document all customizations

## Customization

### Adding Custom Policies
1. Create JSON policy in `databricks-cli/cluster-policies/`
2. Reference in deployment scripts
3. Assign to groups via Python SDK
4. Test with sample cluster creation

### Extending Network Configuration
1. Modify `terraform/networking.tf`
2. Update NSG rules for new services
3. Create additional Private Endpoints
4. Update Private DNS zones

### Adding Monitoring
1. Configure metrics in `monitoring/terraform/`
2. Create dashboards in Azure Monitor
3. Set up alerts for key metrics
4. Document runbooks for alerts

## Troubleshooting

### Common Issues

**Cannot reach Private Endpoint**
- Check private DNS zone configuration
- Verify NSG rules allow traffic
- Ensure VNet routing is correct
- Check firewall rules

**Storage access denied**
- Verify service principal role assignment
- Check storage account firewall
- Validate storage credential configuration
- Check external location settings

**Cluster startup timeout**
- Check Azure VM quotas
- Verify cluster policy settings
- Review network security groups
- Check resource availability

See `documentation/troubleshooting.md` for detailed solutions.

## References

- [Databricks Azure Documentation](https://docs.databricks.com/en/)
- [Azure Private Link](https://docs.microsoft.com/en-us/azure/private-link/)
- [Unity Catalog](https://docs.databricks.com/en/data-governance/unity-catalog/)
- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/)
- [Databricks Python SDK](https://databricks-sdk-py.readthedocs.io/)

## Support

For issues, feature requests, or questions:
1. Check `documentation/troubleshooting.md`
2. Review Databricks official documentation
3. Contact your Databricks Account Executive
4. Open GitHub issues in your repository

## License

Proprietary - Internal Use Only

## Contributing

1. Create feature branch from `develop`
2. Follow Terraform and Python coding standards
3. Add tests for new functionality
4. Update documentation
5. Submit pull request for review

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | Jan 2026 | Initial release |

---

**Last Updated**: January 2026  
**Maintained By**: Infrastructure Team  
**Status**: Production Ready
