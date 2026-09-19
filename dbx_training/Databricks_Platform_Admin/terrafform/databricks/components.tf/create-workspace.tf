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

##########
# Job variables
##########
variable "job_name" {
  description = "A name for the job."
  type        = string
  default     = "My Job"
}

variable "task_key" {
  description = "A name for the task."
  type        = string
  default     = "my_task"
}

###################
# Cluster Notebooks
###################

variable "notebook_subdirectory" {
  description = "A name for the subdirectory to store the notebook."
  type        = string
  default     = "Terraform"
}

variable "notebook_filename" {
  description = "The notebook's filename."
  type        = string
}

variable "notebook_language" {
  description = "The language of the notebook."
  type        = string
}


####################
# Cluster Variables
####################

variable "cluster_name" {
  description = "A name for the cluster."
  type        = string
  default     = "My Cluster"
}

variable "cluster_autotermination_minutes" {
  description = "How many minutes before automatically terminating due to inactivity."
  type        = number
  default     = 60
}

variable "cluster_num_workers" {
  description = "The number of workers."
  type        = number
  default     = 1
}

# Create the cluster with the "smallest" amount
# of resources allowed.
data "databricks_node_type" "smallest" {
  local_disk = true
}

# Use the latest Databricks Runtime
# Long Term Support (LTS) version.

#################
## For Expression
#################

locals {

  tags ={
    Environment = "Dev"
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


#####################################################
### Azure Resources
#####################################################
# Create Azure Resource Group

# resource "azurerm_resource_group" "rg" {

#   location            = var.region
#   name                = var.resource_group
#   }


#####################################################
### Creating Workspace
#####################################################

resource "azurerm_databricks_workspace" "this" {
  location            = var.region
  name                = var.databrick-wk
  resource_group_name = var.resource_group
  sku                 = var.sku_value
  tags                = local.tags
}

