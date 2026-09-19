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

provider "databricks" {
  # host = azurerm_databricks_workspace.this.workspace_url
  azure_workspace_resource_id =azurerm_databricks_workspace.workspace.id
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


######################################################
### Create instance pool
#####################################################
  # resource "databricks_instance_pool" "pool" {
  #   instance_pool_name = "Pool"
  #   min_idle_instances = 0
  #   max_capacity = 1
  #   node_type_id =  "Standard_DS3_v2"
  #   idle_instance_autotermination_minutes = 10
  # }
#####################################################
### Databricks Components - using Databrickslabs
#####################################################

resource "databricks_cluster" "this" {
  cluster_name            = var.cluster_name
  node_type_id            = "Standard_DS3_v2"
  spark_version           = "15.4.x-scala2.12"
  autotermination_minutes = var.cluster_autotermination_minutes
  num_workers             = var.cluster_num_workers
  
  autoscale {
    min_workers = "1"
    max_workers = "2"
  }
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