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
  node_type_id            = "Standard_L4s"
  spark_version           = "15.4.x-scala2.12"
  autotermination_minutes = var.cluster_autotermination_minutes
  num_workers             = var.cluster_num_workers
  
  autoscale {
    min_workers = "1"
    max_workers = "1"
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

#####################################################
### Create Notebook
#####################################################

resource "databricks_notebook" "this" {
  path     = "/Shared/${var.notebook_subdirectory}/${var.notebook_filename}"
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
    on_success = ["eromonsei.o.samson#gmail.com" ]
    on_failure = [ "eromonsei.o.samson#gmail.com" ]
  }
}

###################################################
## Create a Storage account
###################################################
resource "azurerm_storage_account" "databricks_storage" {
  name                     = "databricksstorageacct"
  resource_group_name      = var.resource_group
  location                 = var.region
  account_tier             = "Standard"
  account_replication_type = "LRS"

  blob_properties {
    delete_retention_policy {
      days    = 1
    }
  }

  tags = {
    environment = "dev"
    project     = "databricks"
  }
}

resource "azurerm_storage_container" "container" {
  name =   "azuredbcomtainer-dev"
  storage_account_id= azurerm_storage_account.databricks_storage.id
}


####################################################
## Creating reates an Azure Key Vault to securely manage secrets like the storage account keys.
####################################################

resource "azurerm_key_vault" "keyvault" {
  name                        = "azuredbkeylv2026"
  resource_group_name      = var.resource_group
  location                 = var.region
  enabled_for_disk_encryption = true
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days  = 7
  purge_protection_enabled    = false

  sku_name = "standard"
}

# Set Key Policies for Key vault
# Access policies are set for the authenticated user to allow actions like getting and setting secrets.
resource "azurerm_key_vault_access_policy" "kv" {
    object_id = data.azurerm_client_config.current.object_id
    tenant_id = data.azurerm_client_config.current.tenant_id
    key_vault_id = azurerm_key_vault.keyvault.id
    secret_permissions = ["Get","List","Set","Delete"]
}

####################################################
## Creating Mount
####################################################
resource "databricks_secret_scope" "db_scope2" {
  name = "dbscope_dev"
  keyvault_metadata  {
    resource_id = azurerm_key_vault.keyvault.id
    dns_name = azurerm_key_vault.keyvault.vault_uri
    
  }
  
}

resource "azurerm_key_vault_secret" "secret" {
    name = "azuredb-test2"
    value = azurerm_storage_account.databricks_storage.primary_access_key
    key_vault_id = azurerm_key_vault.keyvault.id
}


##########################################################################################
## Creating a Mount to the container retrieving access key using AKV backed secret scope
#########################################################################################
resource "databricks_azure_blob_mount" "blob" {
  depends_on = [azurerm_databricks_workspace.this]
  container_name = azurerm_storage_container.container.name
  storage_account_name = azurerm_storage_account.databricks_storage.name
  mount_name = "custommount2"
  auth_type = "ACCESS_KEY"
  token_secret_scope = databricks_secret_scope.db_scope2.name
  token_secret_key = azurerm_key_vault_secret.secret.value
}

#####################################################
### Outputs layer
#####################################################

output "job_url" {
  value = databricks_job.this.url
}

output "notebook_url" {
 value = databricks_notebook.this.url
}

output "databrick_workspace" {
  value = azurerm_databricks_workspace.this.name
}

output "databrick_user" {
  value = databricks_user.my-user.user_name
}

output "databrick_host" {
  value = "https://${azurerm_databricks_workspace.this.workspace_url}/"
}
