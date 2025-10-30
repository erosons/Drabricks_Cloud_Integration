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
  description = "Security group IDs to attach to the Databricks workspace"
  type        = list(string)
  default     = []
}

variable "environment" {
  description = "Deployment environment (e.g., dev, test, prod)"
  type        = string
  default     = "dev"
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

variable "databricks_account_id" {
  description = "Your Databricks Account ID (from the Account Console)"
  type        = string
  
}

variable "vpce_id_frontend"            { type = string }
variable "vpce_id_backend_workspace"    { type = string }
variable "vpce_id_backend_scc"          { type = string }

variable "workspace_vpc_id"            { type = string }
variable "workspace_subnet_ids"        { type = list(string) }
variable "workspace_security_group_id" { type = string }

variable "private_access_public_enabled" { 
  type = bool   
  default = false 
  } # block public


// Optional generic name that other resources may reference
variable "name" {
  description = "Optional name to apply to created resources"
  type        = string
  default     = null
}



# variable "aws_region"            { default = "us-east-1" }
# variable "databricks_account_id" { type = string }

# # Get these per-region from Databricks' "PrivateLink VPC endpoint services" table
# # (workspace front-end/back-end) and SCC relay service names:
# variable "svc_name_workspace" {
#   type = string
#   # example (placeholder!): "com.amazonaws.vpce.us-east-1.vpce-svc-xxxxxxxx"
# }
# variable "svc_name_scc_relay" {
#   type = string
#   # example (placeholder!): "com.amazonaws.vpce.us-east-1.vpce-svc-yyyyyyyy"
# }


# Sanity checklist (AWS)

# Ports / SGs: Allow 443 (REST, web), 6666 (SCC relay), and 8443–8451 internally as per Databricks’ guidance. 
# Databricks Documentation

# Back-end: Two VPCEs in the workspace VPC (Workspace + SCC relay), register both, reference them in the network config. 
# Databricks Documentation

# Front-end: One VPCE in the transit VPC, register it, and attach PAS to the workspace. Then Route 53 A + CNAME records as shown. 
# Databricks Documentation

# Enforcement: In PAS set public_access_enabled = false to force front-end over PrivateLink only. 
# Databricks Documentation

# Customer-managed VPC + SCC enabled are prerequisites.