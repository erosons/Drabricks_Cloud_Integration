terraform {
  required_version = ">= 1.5"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 2.0"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.azure_subscription_id
  tenant_id       = var.azure_tenant_id
  client_id       = var.azure_client_id
  client_secret   = var.azure_client_secret
}

provider "azuread" {
  tenant_id = var.azure_tenant_id
}

# Databricks workspace-level resources require the workspace to be provisioned first.
# Two-phase apply:
#   1. terraform apply -target=azurerm_databricks_workspace.main
#   2. Export DATABRICKS_AZURE_RESOURCE_ID (or DATABRICKS_HOST + DATABRICKS_TOKEN)
#   3. terraform apply
#
# Environment variables for Azure AD auth (recommended):
#   DATABRICKS_AZURE_RESOURCE_ID — workspace ARM resource ID
#   ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID — service principal credentials
provider "databricks" {
}
