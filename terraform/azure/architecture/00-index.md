# Azure Databricks Terraform — Documentation Index

Read these documents in order. Each builds on the previous.

| # | File | What it covers | Time |
|---|------|---------------|------|
| — | [README.md](README.md) | Directory structure, module reference, ABAC layer, two-phase apply, quick start | 15 min |
| 1 | [01-overview.md](01-overview.md) | Architecture layers, infrastructure decisions, security highlights, cost estimates | 10 min |
| 2 | [02-technical-guide.md](02-technical-guide.md) | Networking, storage, Unity Catalog, cluster policies — deep technical detail | 20 min |
| 3 | [03-deployment.md](03-deployment.md) | Step-by-step deployment, prerequisites, validation checklist, troubleshooting | 15 min |
| 4 | [04-gitops-cicd.md](04-gitops-cicd.md) | Remote state, GitOps branch strategy, GitHub Actions CI/CD pipelines | 15 min |
| 5 | [05-reference.md](05-reference.md) | Quick-reference command library (Terraform, Azure CLI, Databricks CLI) | Reference |

## Where to start

**Deploying for the first time?** Read `README.md` → `03-deployment.md`.

**Understanding the design?** Read `01-overview.md` → `02-technical-guide.md`.

**Setting up CI/CD?** Read `04-gitops-cicd.md`.

**Looking for a specific command?** Jump to `05-reference.md`.

## Repository layout (summary)

```
terraform/azure/
├── backend.tf                  # AzureRM remote-state backend (no values — use -backend-config)
├── main.tf                     # Root: VNet, storage, workspace, Unity Catalog, cluster policies
├── providers.tf                # azurerm ~3.0, azuread ~2.0, databricks ~1.0
├── variables.tf                # All root variables
├── outputs.tf                  # workspace_url, workspace_id, vnet_id, SP credentials
├── environments/
│   ├── dev/dev.tfvars
│   └── prd/prd.tfvars
├── modules/
│   ├── networking/
│   ├── storage/
│   ├── cluster_policies/
│   ├── access_groups/
│   ├── catalog/
│   ├── row_filters/
│   ├── column_masks/
│   └── table_grants/
├── abac/                       # Standalone ABAC root (deploy after root module)
├── scripts/
│   ├── 01_setup_terraform_state.sh
│   ├── deploy.sh
│   └── scim_group_manager.py
└── architecture/               # ← You are here
```
