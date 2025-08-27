terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.34"
    }
  }
}

provider "aws" {
  region  = var.aws_region
  #profile = var.aws_profile # optional, if you use AWS named profiles
  
}

provider "databricks" {
  alias = "mws"
  host  = "https://accounts.cloud.databricks.com"
  account_id = var.databricks_account_id
  client_id = var.client_id
  client_secret = var.client_secret
}

# # Workspace-level provider for workspace resources
# provider "databricks" {
#   profile = "WS"
# }