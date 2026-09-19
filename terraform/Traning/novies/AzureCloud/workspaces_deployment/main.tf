terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
    databricks = {
      source = "databricks/databricks"
      version = "~> 1.34.0" # Use the latest stable version or your required version
    }
  }
}

#####################
#Authentication layer
#####################

provider "azurerm" {
  features {
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
  subscription_id = var.subscription_id
}


################################
# # The data "azurerm_client_config" "current" block retrieves 
## information about the authenticated Azure account, such as tenant_id and object_id.
################################

data "azurerm_client_config" "current" {}


####################################################
## Azure Resources -Create Azure Resource Group
####################################################

resource "azurerm_resource_group" "rg" {

  location = var.region
  name     = var.resource_group
}


#####################################################
### Creating Workspace
#####################################################

resource "azurerm_databricks_workspace" "this" {
  location            = var.region
  name                = "${var.workspace_name}-${random_integer.number.result}"
  resource_group_name = var.resource_group
  sku                 = var.sku_value
  tags                = var.tags
  depends_on = [azurerm_resource_group.rg]

}
