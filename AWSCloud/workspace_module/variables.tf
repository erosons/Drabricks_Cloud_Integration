variable "aws_region" {
  description = "AWS region for the workspace"
  type        = string
  default     = "us-east-1"
}

variable "workspace_name_prefix" {
  description = "Prefix for workspace name"
  type        = string
  default     = "my-dbworkspace"
}

variable "bucket_name_prefix" {
  description = "Your Databricks Account ID (from the Account Console)"
    type        = string
}
  
variable "tf_backend_bucket" {
  description = "Your Databricks Account ID (from the Account Console)"
  type        = string
}


# optional: if you prefer using AWS named profile
variable "access_connector_prefix" {
  description = "AWS named profile"
  type        = string
  default     = null
}

variable "dynamodb_table_name" {
  description = "DynamoDB table name for terraform state locking"
  type        = string
  default     = "dbx-remote-state-lock"
}


variable "tags" {
  type        = map(string)
  description = "Additional tags applied to all resources created"
  default     = {}
}

# Stage 2 (workspace-level) variables you'll set AFTER the workspace is created
variable "databricks_account_id" {
  description = "Account Id that could be found in the top right corner of https://accounts.cloud.databricks.com/"
}

# optional: if you prefer using AWS named profile
variable "network_prefix" {
  description = "AWS named profile"
  type        = string
  default     = null
}


variable "vpc_id" {
  description = "VPC ID where the Databricks workspace will be deployed"
  type        = string
}
variable "subnets_private_ids" {
  description = "List of subnet IDs within the VPC for the Databricks workspace"
  type        = list(string)
}
variable "security_group_ids" {
  description = "Security group ID to attach to the Databricks workspace"
  type        = string
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