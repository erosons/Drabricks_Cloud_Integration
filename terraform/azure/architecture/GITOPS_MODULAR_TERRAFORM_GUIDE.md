# GITOPS & MODULAR TERRAFORM IMPLEMENTATION GUIDE

**Complete Guide to State Management, Modular Architecture, and GitOps Deployment**

---

## TABLE OF CONTENTS

1. Terraform State Management
2. Modular Architecture
3. GitOps Workflow
4. CI/CD Pipeline Setup
5. Deployment Patterns
6. Module Usage Examples
7. Best Practices

---

## 1. TERRAFORM STATE MANAGEMENT

### 1.1 State File Location Strategy

**Problem**: Local state files are not shared and difficult to manage in teams.

**Solution**: Store state in Azure Storage Account with versioning and locking.

#### Azure Storage Backend Setup

```bash
# Step 1: Run state initialization script
bash scripts/01_setup_terraform_state.sh

# This creates:
# - Resource group for state management
# - Storage account (tfstate{timestamp})
# - Container (tfstate)
# - Enables versioning and soft delete
# - Generates backend-config.hcl
```

#### Backend Configuration File

**Location**: `terraform/backend-config.hcl`

```hcl
resource_group_name  = "terraform-state"
storage_account_name = "tfstatexxxxx"
container_name       = "tfstate"
key                  = "terraform.tfstate"
```

#### Initialize Terraform with Remote Backend

```bash
cd terraform

# Initialize with remote state
terraform init -backend-config=backend-config.hcl

# Verify state is remote
terraform state list

# Check state file in Azure
az storage blob list \
  --container-name tfstate \
  --account-name tfstatexxxxx \
  --account-key $ARM_ACCESS_KEY
```

### 1.2 State File Locking

**Automatic State Locking**: Azure Storage provides lease-based locking automatically.

```bash
# View state lock (if locked)
az storage blob show \
  --container-name tfstate \
  --name terraform.tfstate.lock.hcl \
  --account-name tfstatexxxxx \
  --account-key $ARM_ACCESS_KEY

# Force unlock (use carefully)
az storage blob lease break \
  --container-name tfstate \
  --blob-name terraform.tfstate.lock.hcl \
  --account-name tfstatexxxxx \
  --account-key $ARM_ACCESS_KEY
```

### 1.3 State File Versioning

**Benefit**: Rollback capability if deployment fails

```bash
# List all versions
az storage blob list-versions \
  --container-name tfstate \
  --account-name tfstatexxxxx \
  --account-key $ARM_ACCESS_KEY

# Restore specific version
az storage blob copy start \
  --account-name tfstatexxxxx \
  --account-key $ARM_ACCESS_KEY \
  --source-uri "https://tfstatexxxxx.blob.core.windows.net/tfstate/terraform.tfstate?snapshot=2024-01-20T10:00:00Z" \
  --destination-container tfstate \
  --destination-blob terraform.tfstate
```

### 1.4 Environment Variables for State Access

**File**: `.env` (in .gitignore)

```bash
# Azure Authentication
export AZURE_SUBSCRIPTION_ID="your-subscription-id"
export AZURE_TENANT_ID="your-tenant-id"
export AZURE_CLIENT_ID="your-client-id"
export AZURE_CLIENT_SECRET="your-client-secret"

# Terraform State Access
export ARM_ACCESS_KEY="your-storage-key"
export TF_LOG=INFO
```

---

## 2. MODULAR ARCHITECTURE

### 2.1 Module Structure

```
terraform/
├── modules/
│   ├── networking/
│   │   ├── main.tf          # Network resources
│   │   ├── variables.tf      # Input variables
│   │   ├── outputs.tf        # Output values
│   │   └── README.md         # Module documentation
│   ├── storage/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── README.md
│   ├── cluster_policies/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── README.md
│   └── compute/
│       ├── main.tf
│       ├── variables.tf
│       ├── outputs.tf
│       └── README.md
├── environments/
│   ├── prod/
│   │   ├── main.tf
│   │   ├── terraform.tfvars
│   │   └── outputs.tf
│   ├── staging/
│   │   ├── main.tf
│   │   ├── terraform.tfvars
│   │   └── outputs.tf
│   └── dev/
│       ├── main.tf
│       ├── terraform.tfvars
│       └── outputs.tf
├── root/
│   ├── main.tf              # Root module (orchestrates all)
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── backend-config.hcl       # State configuration
└── versions.tf              # Provider versions
```

### 2.2 Module Usage

#### Networking Module

```hcl
module "networking" {
  source = "./modules/networking"

  environment             = "prod"
  project_name            = "databricks"
  location                = "eastus"
  resource_group_name     = azurerm_resource_group.main.name
  vnet_address_space      = ["10.0.0.0/16"]
  public_subnet_prefix    = "10.0.0.0/24"
  private_subnet_prefix   = "10.0.1.0/24"
  enable_private_endpoints = true
  common_tags             = var.common_tags
}
```

#### Storage Module

```hcl
module "storage" {
  source = "./modules/storage"

  environment                    = "prod"
  project_name                   = "databricks"
  location                        = "eastus"
  resource_group_name             = azurerm_resource_group.main.name
  storage_replication_type        = "GRS"
  enabled_blob_versioning        = true
  create_separate_data_storage    = true
  allowed_subnet_ids              = [module.networking.private_subnet_id]
  private_subnet_id               = module.networking.private_subnet_id
  enable_private_endpoints        = true
  common_tags                     = var.common_tags

  depends_on = [module.networking]
}
```

#### Cluster Policies Module

```hcl
module "cluster_policies" {
  source = "./modules/cluster_policies"

  environment                 = "prod"
  create_prod_policy          = true
  prod_spark_version          = "13.3.x-scala2.12"
  prod_driver_node_type       = "Standard_DS4_v2"
  prod_worker_node_type       = "Standard_DS4_v2"
  prod_num_workers            = 2
  prod_worker_range           = [1, 10]
  prod_autotermination_minutes = 30
  prod_autotermination_range  = [10, 120]

  depends_on = [azurerm_databricks_workspace.main]
}
```

### 2.3 Module Composition

**Selective Module Usage**: Choose which modules to deploy

```hcl
# Root main.tf
locals {
  modules_to_deploy = {
    networking         = true
    storage            = true
    cluster_policies   = true
    compute            = true
    sql_warehouse      = false  # Optional
  }
}

# Conditionally create modules
module "networking" {
  count  = local.modules_to_deploy.networking ? 1 : 0
  source = "./modules/networking"
  # ...
}

module "storage" {
  count  = local.modules_to_deploy.storage ? 1 : 0
  source = "./modules/storage"
  # ...
  depends_on = local.modules_to_deploy.networking ? [module.networking[0]] : []
}
```

---

## 3. GITOPS WORKFLOW

### 3.1 Git Repository Structure

```
databricks-terraform/
├── .github/
│   └── workflows/
│       ├── validate.yml           # Syntax & security checks
│       ├── plan.yml               # Terraform plan on PR
│       ├── apply-staging.yml      # Auto-apply to staging
│       ├── apply-prod.yml         # Manual apply to prod
│       └── destroy.yml            # Cleanup job
├── terraform/
│   └── (module structure above)
├── scripts/
│   ├── 01_setup_terraform_state.sh
│   ├── 02_validate_modules.sh
│   └── 03_deploy.sh
├── .gitignore
├── .terraform-version            # Pin Terraform version
├── README.md
└── DEPLOYMENT_GUIDE.md
```

### 3.2 Git Workflow

#### Branch Strategy

```
main (production)
  ↑
  ├─ staging (integration)
  │   ↑
  │   └─ feature/xxxxx (development)
  │
  └─ hotfix/xxxxx (emergency fixes)
```

#### Commit Convention

```bash
# Commit messages follow pattern:
# [MODULE] DESCRIPTION

# Examples:
git commit -m "[networking] Add private endpoints configuration"
git commit -m "[storage] Enable blob versioning"
git commit -m "[cluster-policies] Add production policy"
git commit -m "[all] Update common tags"
```

### 3.3 Pull Request Workflow

```
1. Create feature branch
   git checkout -b feature/add-sql-warehouse

2. Make changes to modules
   # Edit terraform/modules/compute/main.tf
   # Edit terraform/environments/prod/terraform.tfvars

3. Validate locally
   terraform validate
   terraform fmt -recursive

4. Push and create PR
   git push origin feature/add-sql-warehouse
   # GitHub automatically runs validate workflow

5. Review PR
   # Check GitHub Actions logs
   # Review terraform plan output

6. Merge to main
   # After approval, merge PR
   # GitHub automatically runs apply workflow
```

---

## 4. CI/CD PIPELINE SETUP

### 4.1 GitHub Actions Workflow Files

#### validate.yml - Syntax & Security Checks

```yaml
name: Terraform Validate

on:
  push:
    branches: [main, staging]
  pull_request:
    branches: [main, staging]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.5.0
      
      - name: Terraform Format
        run: |
          cd terraform
          terraform fmt -recursive -check
      
      - name: Terraform Validate
        run: |
          cd terraform
          terraform validate
      
      - name: TFLint
        uses: terraform-linters/setup-tflint@v3
        
      - name: Run TFLint
        run: |
          cd terraform
          tflint --recursive
```

#### plan.yml - Generate Terraform Plan

```yaml
name: Terraform Plan

on:
  pull_request:
    branches: [main, staging]

env:
  ARM_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
  ARM_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
  ARM_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
  ARM_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  ARM_ACCESS_KEY: ${{ secrets.TF_STATE_ACCESS_KEY }}

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.5.0
      
      - name: Terraform Init
        run: |
          cd terraform
          terraform init -backend-config=backend-config.hcl
      
      - name: Terraform Plan
        run: |
          cd terraform
          terraform plan -out=tfplan -json > plan.json
        env:
          TF_VAR_environment: "staging"
      
      - name: Comment PR with Plan
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const plan = fs.readFileSync('terraform/plan.json', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: '```\n' + plan + '\n```'
            })
```

#### apply-prod.yml - Manual Production Apply

```yaml
name: Apply to Production

on:
  workflow_dispatch:  # Manual trigger only
    inputs:
      environment:
        description: 'Environment'
        required: true
        default: 'prod'

env:
  ARM_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
  ARM_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
  ARM_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
  ARM_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  ARM_ACCESS_KEY: ${{ secrets.TF_STATE_ACCESS_KEY }}

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: production  # Require approval
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: 1.5.0
      
      - name: Terraform Init
        run: |
          cd terraform
          terraform init -backend-config=backend-config.hcl
      
      - name: Terraform Apply
        run: |
          cd terraform
          terraform apply -auto-approve -lock=true
        env:
          TF_VAR_environment: "prod"
      
      - name: Post Deployment Validation
        run: |
          bash scripts/03_validate_deployment.sh
      
      - name: Notify Slack
        uses: slackapi/slack-github-action@v1
        with:
          webhook-url: ${{ secrets.SLACK_WEBHOOK }}
          payload: |
            {
              "text": "✅ Production deployment completed",
              "blocks": [
                {
                  "type": "section",
                  "text": {
                    "type": "mrkdwn",
                    "text": "*Deployment Completed*\nEnvironment: prod\nCommit: ${{ github.sha }}"
                  }
                }
              ]
            }
```

### 4.2 GitHub Secrets Setup

```bash
# Add these secrets to GitHub repository settings
# Settings → Secrets and variables → Actions

AZURE_CLIENT_ID          # Service principal ID
AZURE_CLIENT_SECRET      # Service principal secret
AZURE_SUBSCRIPTION_ID    # Azure subscription ID
AZURE_TENANT_ID          # Azure tenant ID
TF_STATE_ACCESS_KEY      # Storage account key
SLACK_WEBHOOK            # Slack webhook URL (optional)
```

---

## 5. DEPLOYMENT PATTERNS

### 5.1 Single Environment Deployment

**For dev/testing environment**

```bash
cd terraform

# Configure for dev
export TF_VAR_environment="dev"
export TF_VAR_create_prod_policy="false"
export TF_VAR_create_staging_policy="false"
export TF_VAR_create_dev_policy="true"

# Deploy
terraform init -backend-config=backend-config.hcl
terraform plan -out=dev.plan
terraform apply dev.plan
```

### 5.2 Multi-Environment Deployment

**For prod/staging/dev deployment**

```bash
# Create separate tfvars for each environment
# environments/prod/terraform.tfvars
environment = "prod"
location    = "eastus"
databricks_sku = "premium"

# environments/staging/terraform.tfvars
environment = "staging"
location    = "eastus"
databricks_sku = "standard"

# Deploy each
for ENV in prod staging dev; do
  cd terraform/environments/$ENV
  terraform init -backend-config=../../../backend-config.hcl
  terraform plan -var-file=terraform.tfvars
  terraform apply -var-file=terraform.tfvars
done
```

### 5.3 Selective Module Deployment

**Deploy only specific modules**

```bash
cd terraform

# Deploy only networking
terraform apply -target=module.networking

# Deploy storage after networking
terraform apply -target=module.storage

# Deploy cluster policies
terraform apply -target=module.cluster_policies

# Deploy everything
terraform apply
```

### 5.4 Destroy Infrastructure

**Safely destroy resources**

```bash
cd terraform

# Plan destruction
terraform plan -destroy

# Destroy (requires confirmation)
terraform destroy

# Destroy without confirmation
terraform destroy -auto-approve

# Destroy specific module
terraform destroy -target=module.cluster_policies
```

---

## 6. MODULE USAGE EXAMPLES

### 6.1 Production Setup

```hcl
# terraform/environments/prod/main.tf

module "networking" {
  source = "../../modules/networking"
  
  environment              = "prod"
  project_name             = "databricks"
  location                 = "eastus"
  resource_group_name      = azurerm_resource_group.prod.name
  vnet_address_space       = ["10.0.0.0/16"]
  public_subnet_prefix     = "10.0.0.0/24"
  private_subnet_prefix    = "10.0.1.0/24"
  enable_private_endpoints = true
}

module "storage" {
  source = "../../modules/storage"
  
  environment                    = "prod"
  project_name                   = "databricks"
  location                        = "eastus"
  resource_group_name             = azurerm_resource_group.prod.name
  storage_replication_type        = "GRS"
  create_separate_data_storage    = true
  enable_blob_versioning          = true
  enable_cmk                      = true
  allowed_subnet_ids              = [module.networking.private_subnet_id]
  
  depends_on = [module.networking]
}

module "cluster_policies" {
  source = "../../modules/cluster_policies"
  
  environment = "prod"
  
  # Enable all policy types for production
  create_prod_policy = true
  create_staging_policy = true
  create_dev_policy = true
  create_sql_warehouse_policy = true
  create_interactive_policy = true
  create_job_policy = true
}
```

### 6.2 Staging Setup

```hcl
# terraform/environments/staging/main.tf

module "networking" {
  source = "../../modules/networking"
  
  environment              = "staging"
  project_name             = "databricks"
  location                 = "eastus"
  resource_group_name      = azurerm_resource_group.staging.name
  vnet_address_space       = ["10.1.0.0/16"]
  public_subnet_prefix     = "10.1.0.0/24"
  private_subnet_prefix    = "10.1.1.0/24"
  enable_private_endpoints = true
}

module "storage" {
  source = "../../modules/storage"
  
  environment                    = "staging"
  project_name                   = "databricks"
  location                        = "eastus"
  resource_group_name             = azurerm_resource_group.staging.name
  storage_replication_type        = "LRS"  # Cost optimization
  create_separate_data_storage    = true
  enable_blob_versioning          = true
  enable_cmk                      = false
  allowed_subnet_ids              = [module.networking.private_subnet_id]
  
  depends_on = [module.networking]
}

module "cluster_policies" {
  source = "../../modules/cluster_policies"
  
  environment = "staging"
  
  # Reduced policies for staging
  create_prod_policy = false
  create_staging_policy = true
  create_dev_policy = true
}
```

### 6.3 Development Setup

```hcl
# terraform/environments/dev/main.tf

module "networking" {
  source = "../../modules/networking"
  
  environment              = "dev"
  project_name             = "databricks"
  location                 = "eastus"
  resource_group_name      = azurerm_resource_group.dev.name
  vnet_address_space       = ["10.2.0.0/16"]
  public_subnet_prefix     = "10.2.0.0/24"
  private_subnet_prefix    = "10.2.1.0/24"
  enable_private_endpoints = false  # For cost saving
}

module "storage" {
  source = "../../modules/storage"
  
  environment                    = "dev"
  project_name                   = "databricks"
  location                        = "eastus"
  resource_group_name             = azurerm_resource_group.dev.name
  storage_replication_type        = "LRS"
  create_separate_data_storage    = false  # Cost optimization
  enable_blob_versioning          = false
  allowed_subnet_ids              = []  # No restrictions in dev
  
  depends_on = [module.networking]
}

module "cluster_policies" {
  source = "../../modules/cluster_policies"
  
  environment = "dev"
  
  # Minimal policies for development
  create_prod_policy = false
  create_staging_policy = false
  create_dev_policy = true
}
```

---

## 7. BEST PRACTICES

### 7.1 Module Development

✅ **DO**:
- One responsibility per module
- Document inputs/outputs
- Use consistent naming
- Include examples
- Test modules independently
- Version modules explicitly

❌ **DON'T**:
- Mix resources from different domains
- Hardcode values
- Create circular dependencies
- Ignore outputs
- Leave modules undocumented

### 7.2 State Management

✅ **DO**:
- Store state remotely
- Enable versioning
- Use state locking
- Secure state access
- Regular backups
- Rotate credentials

❌ **DON'T**:
- Commit state files to Git
- Share state files via email
- Store credentials in state
- Disable locking
- Manual state edits

### 7.3 Git & CI/CD

✅ **DO**:
- Require PR reviews
- Run automated tests
- Validate before merge
- Plan before apply
- Tag releases
- Maintain audit trail

❌ **DON'T**:
- Push directly to main
- Apply without plan
- Merge failing tests
- Skip code review
- Manual deployments to prod

### 7.4 Security

✅ **DO**:
- Use service principals
- Rotate credentials
- Enable encryption
- Audit all changes
- Use GitHub secrets
- Apply least privilege

❌ **DON'T**:
- Hardcode credentials
- Share secrets
- Disable encryption
- Use root credentials
- Skip access controls

---

## 8. TROUBLESHOOTING

### State File Issues

```bash
# State locked issue
# Solution: Check for concurrent terraform runs
terraform state unlock

# State corruption
# Solution: Restore from versioning
az storage blob list-versions ...
```

### Module Dependency Issues

```bash
# Check dependency graph
terraform graph | dot -Tpdf > graph.pdf

# See detailed plan with dependencies
terraform plan -out=plan
terraform show plan
```

### Deployment Failures

```bash
# Enable detailed logging
export TF_LOG=DEBUG
terraform apply

# Check workspace logs
az databricks workspace list

# Validate network connectivity
az network nic list-effective-network-security-groups ...
```

---

## SUMMARY

✅ **State**: Azure Storage with versioning and locking  
✅ **Modules**: Networking, Storage, Cluster Policies (reusable)  
✅ **GitOps**: GitHub Actions for automated validation & deployment  
✅ **CI/CD**: Plan on PR, apply on merge  
✅ **Environments**: prod, staging, dev with separate configs  
✅ **Security**: Service principals, encryption, audit logs  

**Next Steps**:
1. Run `bash scripts/01_setup_terraform_state.sh`
2. Create GitHub Actions workflows
3. Add Azure credentials to GitHub Secrets
4. Start deploying with `terraform apply`
