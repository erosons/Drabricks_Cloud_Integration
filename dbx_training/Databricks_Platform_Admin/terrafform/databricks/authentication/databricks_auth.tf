terraform {
  required_providers {
    databricks = {
      source = "databricks/databricks"
    }
  }
}

variable "DATABRICKS_HOST" {
  description = "url"
  type        = string
}

variable "DATABRICKS_TOKEN" {
  description = "TOKEN"
  type        = string
}

provider "databricks" {
  host = var.DATABRICKS_HOST
  token = var.DATABRICKS_TOKEN
  
}

resource "databricks_catalog" "sandbox" {
  name    = "sandbox"
  comment = "this catalog is managed by terraform"
  properties = {
    purpose = "testing"
  }
}
  

resource "databricks_cluster" "this" {
  cluster_name            = "mycluster"
  node_type_id            = "Standard_L4s"
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
output "databrick_workspace" {
  value = databricks_catalog.sandbox.name
}