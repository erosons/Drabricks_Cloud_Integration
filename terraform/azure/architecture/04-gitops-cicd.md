# 04 — GitOps & CI/CD

## Remote State Management

Terraform state is stored in Azure Blob Storage, providing shared access, locking, and versioning.

### Bootstrap (one-time per subscription)

```bash
bash terraform/azure/scripts/01_setup_terraform_state.sh
```

This creates:
- Resource group: `terraform-state`
- Storage account: `tfstate{timestamp}` (Standard LRS, TLS 1.2, versioning on, default-deny firewall)
- Container: `tfstate`
- Output file: `terraform/backend-config.hcl`

### Backend configuration

`backend-config.hcl` (committed to Git, no secrets):

```hcl
resource_group_name  = "terraform-state"
storage_account_name = "tfstatexxxxx"
container_name       = "tfstate"
key                  = "terraform.tfstate"
```

Initialise with:

```bash
terraform init -backend-config=backend-config.hcl
```

### State locking

Azure Blob Storage uses lease-based locking automatically. If a lock is stuck after a failed run:

```bash
# Break a stuck lease
az storage blob lease break \
  --container-name tfstate \
  --blob-name terraform.tfstate \
  --account-name tfstatexxxxx \
  --account-key $ARM_ACCESS_KEY
```

### State versioning and rollback

```bash
# List versions
az storage blob list-versions \
  --container-name tfstate \
  --account-name tfstatexxxxx \
  --account-key $ARM_ACCESS_KEY

# Restore a specific version
az storage blob copy start \
  --account-name tfstatexxxxx \
  --account-key $ARM_ACCESS_KEY \
  --source-uri "https://tfstatexxxxx.blob.core.windows.net/tfstate/terraform.tfstate?snapshot=<snapshot-id>" \
  --destination-container tfstate \
  --destination-blob terraform.tfstate
```

---

## Branch Strategy

```
main ─────────────────────────────── production (auto-apply on merge)
  ↑
  staging ──────────────────────────  integration (auto-apply on merge)
    ↑
    feature/add-new-domain ───────── development branches (plan on PR)
    hotfix/critical-fix ──────────── emergency fixes (plan on PR)
```

**Rules:**
- Direct pushes to `main` are blocked — all changes must go through PR
- PRs to `main` require at least one approval and a passing plan
- Production apply is manual (workflow_dispatch) to allow review of plan output before apply

### Commit convention

```
[module] description

Examples:
[networking] Add private endpoints for storage
[cluster-policies] Increase prod autotermination to 90 min
[abac] Add hr domain row filters
[all] Bump Spark version to 15.4
```

---

## GitHub Actions Workflows

### Required secrets

Configure these in repository Settings → Secrets and variables → Actions:

| Secret | Value |
|---|---|
| `AZURE_CLIENT_ID` | Terraform service principal client ID |
| `AZURE_CLIENT_SECRET` | Terraform service principal client secret |
| `AZURE_SUBSCRIPTION_ID` | Azure subscription ID |
| `AZURE_TENANT_ID` | Azure tenant ID |
| `TF_STATE_ACCESS_KEY` | Storage account access key (from bootstrap script) |

### `.github/workflows/validate.yml`

Runs on every push and PR. Blocks merge if format or validation fails.

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
    defaults:
      run:
        working-directory: terraform/azure

    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.5.0

      - name: Terraform Format Check
        run: terraform fmt -recursive -check

      - name: Terraform Init
        run: terraform init -backend=false

      - name: Terraform Validate
        run: terraform validate

      - name: TFLint
        uses: terraform-linters/setup-tflint@v4

      - name: Run TFLint
        run: tflint --recursive
```

### `.github/workflows/plan.yml`

Runs on PRs. Posts the plan output as a PR comment.

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
    defaults:
      run:
        working-directory: terraform/azure

    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.5.0

      - name: Terraform Init
        run: terraform init -backend-config=../../backend-config.hcl

      - name: Terraform Plan
        id: plan
        run: |
          terraform plan -out=tfplan \
            -var-file=environments/dev/dev.tfvars \
            -no-color 2>&1 | tee plan.txt
        env:
          TF_VAR_azure_client_id: ${{ secrets.AZURE_CLIENT_ID }}
          TF_VAR_azure_client_secret: ${{ secrets.AZURE_CLIENT_SECRET }}
          TF_VAR_azure_subscription_id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          TF_VAR_azure_tenant_id: ${{ secrets.AZURE_TENANT_ID }}

      - name: Comment PR with Plan
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const plan = fs.readFileSync('terraform/azure/plan.txt', 'utf8');
            const truncated = plan.length > 65000 ? plan.slice(0, 65000) + '\n... (truncated)' : plan;
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `### Terraform Plan\n\`\`\`\n${truncated}\n\`\`\``
            });
```

### `.github/workflows/apply-prod.yml`

Manual trigger only (`workflow_dispatch`). Requires environment approval gate.

```yaml
name: Apply to Production

on:
  workflow_dispatch:
    inputs:
      confirm:
        description: 'Type "yes" to confirm production apply'
        required: true

env:
  ARM_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
  ARM_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
  ARM_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
  ARM_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  ARM_ACCESS_KEY: ${{ secrets.TF_STATE_ACCESS_KEY }}

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: production   # requires approval in GitHub environment settings
    if: github.event.inputs.confirm == 'yes'
    defaults:
      run:
        working-directory: terraform/azure

    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.5.0

      - name: Terraform Init
        run: terraform init -backend-config=../../backend-config.hcl

      - name: Phase 1 — Infrastructure
        run: |
          terraform apply -auto-approve \
            -target=azurerm_resource_group.main \
            -target=module.networking \
            -target=module.storage \
            -target=azurerm_databricks_workspace.main \
            -var-file=environments/prd/prd.tfvars
        env:
          TF_VAR_azure_client_id: ${{ secrets.AZURE_CLIENT_ID }}
          TF_VAR_azure_client_secret: ${{ secrets.AZURE_CLIENT_SECRET }}
          TF_VAR_azure_subscription_id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          TF_VAR_azure_tenant_id: ${{ secrets.AZURE_TENANT_ID }}

      - name: Phase 2 — Databricks Configuration
        run: |
          export DATABRICKS_AZURE_RESOURCE_ID=$(terraform output -raw workspace_resource_id)
          terraform apply -auto-approve \
            -var-file=environments/prd/prd.tfvars
        env:
          TF_VAR_azure_client_id: ${{ secrets.AZURE_CLIENT_ID }}
          TF_VAR_azure_client_secret: ${{ secrets.AZURE_CLIENT_SECRET }}
          TF_VAR_azure_subscription_id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
          TF_VAR_azure_tenant_id: ${{ secrets.AZURE_TENANT_ID }}
```

---

## Local Development Workflow

```bash
# 1. Create a feature branch
git checkout -b feature/add-new-domain

# 2. Edit tfvars or module code
vi terraform/azure/environments/dev/dev.tfvars

# 3. Format and validate locally
cd terraform/azure/
terraform fmt -recursive
terraform validate

# 4. Run a plan (set env vars first)
export ARM_ACCESS_KEY="..."
export DATABRICKS_AZURE_RESOURCE_ID="..."
export TF_VAR_azure_client_id="..."
export TF_VAR_azure_client_secret="..."
export TF_VAR_azure_subscription_id="..."
export TF_VAR_azure_tenant_id="..."

terraform plan -var-file=environments/dev/dev.tfvars

# 5. Push and open PR
git push origin feature/add-new-domain
# GitHub Actions runs validate + plan automatically
```

---

## Environment Variable Reference

| Variable | Purpose |
|---|---|
| `ARM_ACCESS_KEY` | Terraform remote state storage account key |
| `ARM_CLIENT_ID` | AzureRM provider auth (alternative to var) |
| `ARM_CLIENT_SECRET` | AzureRM provider auth (alternative to var) |
| `ARM_SUBSCRIPTION_ID` | AzureRM provider auth (alternative to var) |
| `ARM_TENANT_ID` | AzureRM provider auth (alternative to var) |
| `DATABRICKS_AZURE_RESOURCE_ID` | Databricks provider auth (Phase 2 — set from `terraform output workspace_resource_id`) |
| `TF_LOG` | Terraform log level (`INFO`, `DEBUG`, `TRACE`) |
| `TF_VAR_*` | Override any `var.*` variable without a `-var` flag |
