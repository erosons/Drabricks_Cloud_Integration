variable "aws_region" {
  description = "AWS region for the workspace"
  type        = string
  default     = "us-east-1"
}

# Stage 2 (workspace-level) variables you'll set AFTER the workspace is created
variable "databricks_account_id" {
  description = "Account Id that could be found in the top right corner of https://accounts.cloud.databricks.com/"
}

variable  "client_id" {
  description = "OAuth Client ID created in Databricks Account Console"
  type        = string
}
variable  "client_secret" {   
  description = "OAuth Client Secret created in Databricks Account Console"
  type        = string
  sensitive   = true
}

variable "unity_catalog_metastore" {
  description = "Boolean to create Unity Catalog Metastore"
  type        = bool
  default     = true
  
}

variable "metastore_name" {
  description = "Name of the Unity Catalog Metastore"
  type        = string
  default     = "my-metastore"
}