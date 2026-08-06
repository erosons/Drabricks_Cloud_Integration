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

#####################
#Authentication layer
#####################

provider "azurerm" {
  features {}
  subscription_id ="948bd2bd-6f43-41f7-872c-d3a8c2b0656a"

}

################################
# # The data "azurerm_client_config" "current" block retrieves information about the authenticated Azure account, such as tenant_id and object_id.
################################

data "azurerm_client_config" "current" {}

################################
# Get workspace if information were already exists
################################

data "azurerm_databricks_workspace" "this" {
  name                = "databricks-warehous3"
  resource_group_name = "databricks"
}

#######################################
#Authentication into Databricks
######################################
# The databricks provider uses the workspace URL and Azure resource ID to authenticate and interact with the Databricks environment.
provider "databricks" {
  host                        = data.azurerm_databricks_workspace.this.workspace_url
  azure_workspace_resource_id = data.azurerm_databricks_workspace.this.id
}

resource "databricks_catalog" "sandbox" {
  name    = "sandbox2"
  comment = "this catalog is managed by terraform"
  properties = {
    purpose = "testing"
  }
}

resource "databricks_user" "my-user" {
  user_name    = "new_user@databricks.com"
  display_name = "Test User"
}


output "databricks_workspace_id" {
  value = data.azurerm_databricks_workspace.this.workspace_id
}