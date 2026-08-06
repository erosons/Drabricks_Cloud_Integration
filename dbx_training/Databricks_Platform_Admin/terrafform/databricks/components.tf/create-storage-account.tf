terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
    }
    databricks = {
      source  = "databricks/databricks"
    }
  }
}

#####################
#Authentication layer
#####################

provider "azurerm" {
  features {}
  subscription_id ="948bd2bd-6f43-41f7-872c-d3a8c2b0656a"
  client_id = 
  client_secret = 
  tenant_id = 

}

# provider "azurerm" {
#   features {}
# }

# Resource Group
resource "azurerm_resource_group" "rg" {
  name     = "databricks-rg"
  location = "East US"
}

# Storage Account
resource "azurerm_storage_account" "databricks_storage" {
  name                     = "databricksstorageacct"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  blob_properties {
    delete_retention_policy {
      days    = 0
    }
  }

  tags = {
    environment = "dev"
    project     = "databricks"
  }
}