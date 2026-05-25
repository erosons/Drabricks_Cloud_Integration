# Remote state backend — populate via -backend-config flag or environment variables.
# Bootstrap the storage account first with scripts/01_setup_terraform_state.sh,
# then initialise: terraform init -backend-config=backend-config.hcl
#
# backend-config.hcl (not committed):
#   resource_group_name  = "terraform-state"
#   storage_account_name = "tfstate<suffix>"
#   container_name       = "tfstate"
#   key                  = "azure/databricks.tfstate"
#
# Alternatively set ARM_ACCESS_KEY in the environment.

terraform {
  backend "azurerm" {
  }
}
