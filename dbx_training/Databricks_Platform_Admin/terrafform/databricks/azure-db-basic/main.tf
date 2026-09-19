terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
    databricks = {
      source = "databricks/databricks"
    }
  }
}

# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = var.resource_group_name
  location = var.location
}

# Databricks Workspace
resource "azurerm_databricks_workspace" "databricks" {
  name                = var.databricks_workspace_name
  resource_group_name = azurerm_resource_group.rg.name
  location            = azurerm_resource_group.rg.location
  sku                 = "standard"
}

# Storage Account with Hierarchical Namespace (ADLS Gen2)
resource "azurerm_storage_account" "storage" {
  name                     = var.storage_account_name
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  # Enable Hierarchical Namespace for ADLS Gen2
  enable_hierarchical_namespace = true
}

# Storage Container
resource "azurerm_storage_container" "container" {
  name                  = var.container_name
  storage_account_name  = azurerm_storage_account.storage.name
  container_access_type = "private"
}

# Role Assignment for Databricks Managed Identity on Storage Container
resource "azurerm_role_assignment" "databricks_contributor" {
  scope                = azurerm_storage_container.container.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_databricks_workspace.databricks.managed_service_principal_id
}
