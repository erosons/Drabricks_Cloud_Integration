terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.0.0"
    }
    azurerm = {
      source  = "hashicorp/azurerm"
      version = ">= 3.0.0"
    }
  }
}

provider "azurerm" {
  features {}
}

provider "databricks" {
  host                        = data.azurerm_databricks_workspace.existing_workspace.workspace_url
  azure_workspace_resource_id = data.azurerm_databricks_workspace.existing_workspace.id
}

# Fetch the existing Databricks workspace
data "azurerm_databricks_workspace" "existing_workspace" {
  name                = "your-existing-workspace-name"    # Replace with your workspace name
  resource_group_name = "your-resource-group-name"        # Replace with your resource group name
}

# Define SQL Warehouse (SQL Endpoint) Configuration
resource "databricks_sql_endpoint" "sql_warehouse" {
  name                  = "sql-warehouse"
  cluster_size          = "2X-Small"     # Adjust based on workload requirements
  min_num_clusters      = 1
  max_num_clusters      = 2
  auto_stop_mins        = 15             # Auto-stop after 15 mins of inactivity
  enable_serverless_compute = true      # Set to true if serverless compute is supported and required

   tags {
    custom_tags {
      key   = "City"
      value = "Amsterdam"
    }
  }
}

# Outputs to display SQL Warehouse details
output "sql_warehouse_name" {
  value = databricks_sql_endpoint.sql_warehouse.name
}

output "sql_warehouse_id" {
  value = databricks_sql_endpoint.sql_warehouse.id
}
