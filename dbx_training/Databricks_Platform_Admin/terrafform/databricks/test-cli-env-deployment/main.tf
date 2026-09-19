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

data "databricks_current_user" "me" {
}

###################
# Cluster Variables
##################

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
data "databricks_spark_version" "latest_lts" {
  long_term_support = true
}

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
  subscription_id = var.ARM_TENANT_ID

}

provider "databricks" {
  host = azurerm_databricks_workspace.this.workspace_url
}


#####################################################
### Azure Resources
#####################################################
# Create Azure Resource Group

resource "azurerm_resource_group" "rg" {

  location            = var.region
  name                = var.resource_group
  }


#####################################################
### Creating Workspace
#####################################################

resource "azurerm_databricks_workspace" "this" {
  location            = var.region
  name                = "${var.databrick-wk}-dev"
  resource_group_name = var.resource_group
  sku                 = var.sku_value
  tags                = local.tags
}

#####################################################
### Databricks Components - using Databrickslabs
#####################################################

resource "databricks_cluster" "this" {
  cluster_name            = var.cluster_name
  node_type_id            = data.databricks_node_type.smallest.id
  spark_version           = data.databricks_spark_version.latest_lts.id
  autotermination_minutes = var.cluster_autotermination_minutes
  num_workers             = var.cluster_num_workers
 
  # Add Libraries
  library {
    pypi {
      package = "pyodbc"
    }
  }
  # Add Libraries
  custom_tags = {
    Department ="dev"
  }
}

#####################################################
### Create Notebook
#####################################################

resource "databricks_notebook" "this" {
  content_base64 = base64encode("print('Welcome Databricks Users')")
  path     = "${data.databricks_current_user.me.home}/${var.notebook_subdirectory}/${var.notebook_filename}"
  language = var.notebook_language
  source   = "./${var.notebook_filename}"
}

#####################################################
### Create Users
#####################################################
resource "databricks_user" "my-user" {
  user_name = "test-user@databricks.com"
  display_name = "Test demo user"
}


#####################################################
### Create databricks Job
#####################################################

resource "databricks_job" "this" {
  name = var.job_name
  task {
    task_key = var.task_key
    existing_cluster_id = databricks_cluster.this.cluster_id
    notebook_task {
      notebook_path = databricks_notebook.this.path
    }
  }
  email_notifications {
    on_success = [ data.databricks_current_user.me.user_name ]
    on_failure = [ data.databricks_current_user.me.user_name ]
  }
}

output "job_url" {
  value = databricks_job.this.url
}

#####################################################
### Outputs layer
#####################################################

output "notebook_url" {
 value = databricks_notebook.this.url
}

output "current_user_name" {
  value = data.databricks_current_user.me.user_name
}

output "resource_group_name" {
  value = azurerm_resource_group.rg.name
}

output "databrick_workspace" {
  value = azurerm_databricks_workspace.this.name
}

output "databrick_user" {
  value = databricks_user.my-user.user_name
}

output "databrick_host" {
  value = "https://${azurerm_databricks_workspace.this.workspace_url}"
}

# Output the current Databricks user's display name
output "current_user_name" {
  value = data.databricks_current_user.me.user_name
}


# Retrieve information about the current Databricks user
data "databricks_current_user" "me" {}
