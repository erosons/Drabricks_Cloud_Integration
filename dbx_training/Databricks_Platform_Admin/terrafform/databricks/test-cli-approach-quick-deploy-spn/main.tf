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


#########################
# Input Parameters layer
#########################


variable "databrick-wk" {
  description = "workspaces."
  type        = string
}

variable "sku_value" {
  description = "The sku version"
  type        = string
}

variable "resource_group" {
  description = "resource group deployment."
  type        = string
}

variable "region" {
  description = "resource location"
  type        = string
}

variable "ARM_TENANT_ID" {
  description = "resource location"
  type        = string
}

variable "ARM_CLIENT_ID" {
  description = "resource location"
  type        = string
}

variable "ARM_CLIENT_SECRET" {
  description = "resource location"
  type        = string
}



#################
## For Expression
#################

locals {

  tags ={
    Environment = "prd"
    Owner       = "Samson Eromonsei"
    Env_Prefix  = "dev-${var.databrick-wk}"
    Source      = "Terraform"
  }
}

#####################
#Authentication layer
#####################

provider "azurerm" {
  features {}
  subscription_id ="948bd2bd-6f43-41f7-872c-d3a8c2b0656a"
  client_id = var.ARM_CLIENT_ID
  client_secret = var.ARM_CLIENT_SECRET
  tenant_id = var.ARM_TENANT_ID

}

################################
# # The data "azurerm_client_config" "current" block retrieves information about the authenticated Azure account, such as tenant_id and object_id.
################################

data "azurerm_client_config" "current" {}

# provider "databricks" {
#   # host = azurerm_databricks_workspace.this.workspace_url
#   azure_workspace_resource_id =azurerm_databricks_workspace.workspace.id
# }


####################################################
## Azure Resources -Create Azure Resource Group
####################################################

resource "azurerm_resource_group" "rg" {

  location            = var.region
  name                = var.resource_group
  }


#####################################################
### Creating Workspace
#####################################################

resource "azurerm_databricks_workspace" "this" {
  location            = "West US"
  name                = "${var.databrick-wk}-prd"
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = var.sku_value
  tags                = local.tags
}


#######################################
#Authentication into Databricks
######################################
# The databricks provider uses the workspace URL and Azure resource ID to authenticate and interact with the Databricks environment.
provider "databricks" {
  host                        = azurerm_databricks_workspace.this.workspace_url
  azure_workspace_resource_id = azurerm_databricks_workspace.this.id
}



###################################################
## Create a Storage account
###################################################
resource "azurerm_storage_account" "databricks_storage" {
  name                     = "databricksstorageacct"
  resource_group_name      = azurerm_resource_group.rg.name
  location                 = "West US"
  account_tier             = "Standard"
  account_replication_type = "LRS"
  is_hns_enabled = true

  blob_properties {
    delete_retention_policy {
      days    = 1
    }
  }

  tags = {
    environment = "prd"
    project     = "databricks"
  }
}

resource "azurerm_storage_container" "container" {
  name =   "azuredbcomtainer-prd"
  storage_account_id= azurerm_storage_account.databricks_storage.id
}


#####################################################
### Outputs layer
#####################################################


output "databrick_workspace" {
  value = azurerm_databricks_workspace.this.name
}

output "databrick_host" {
  value = "https://${azurerm_databricks_workspace.this.workspace_url}/"
}
