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

#####################
#Authentication layer (# You have to authertic az with SPN )
# az login --service-principal -u CLIENT_ID  -p CLIENT_SECRET  --tenant TENANT_ID
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

resource "databricks_catalog" "bronze" {
  name    = "bronze"
  comment = "this catalog is managed by terraform"
  properties = {
    purpose = "testing"
  }
}

resource "databricks_schema" "things2" {
  catalog_name = databricks_catalog.bronze.id
  name         = "things2"
  comment      = "this database is managed by terraform"
  properties = {
    kind = "various"
  }
}

# creating a cluster
resource "databricks_cluster" "this" {
  cluster_name            = "mycluster"
  node_type_id            = "Standard_DS3_v2"
  spark_version           = "15.4.x-scala2.12"
  idempotency_token       = "compliance_cluster01"
  autotermination_minutes = 20
  num_workers             = 1
  
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

output "databricks_workspace_id" {
  value = data.azurerm_databricks_workspace.this.workspace_id
}
output "databricks_schema_id" {
  value = databricks_schema.things2.id
}