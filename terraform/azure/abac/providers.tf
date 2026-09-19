terraform {
  required_version = ">= 1.5.0"

  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.38.0"
    }
  }

  # Replace with your backend — S3, AzureRM, or GCS
  backend "s3" {
    bucket         = "your-tfstate-bucket"
    key            = "databricks-abac/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

# Account-level provider — used for group management and metastore
provider "databricks" {
  alias         = "account"
  host          = "https://accounts.azuredatabricks.net"   # or accounts.cloud.databricks.com for AWS
  account_id    = var.databricks_account_id
  client_id     = var.databricks_account_client_id
  client_secret = var.databricks_account_client_secret
}

# Workspace-level provider — used for grants, functions, table policies
provider "databricks" {
  alias         = "workspace"
  host          = var.databricks_workspace_url
  client_id     = var.databricks_workspace_client_id
  client_secret = var.databricks_workspace_client_secret
}
