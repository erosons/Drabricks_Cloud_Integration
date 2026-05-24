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

# variable "vpc_id" {
#   description = "VPC ID where the Databricks workspace will be deployed"
#   type        = string
# }
# variable "subnets_private_ids" {
#   description = "List of subnet IDs within the VPC for the Databricks workspace"
#   type        = list(string)
# }
# variable "security_group_ids" {
#   description = "Security group ID to attach to the Databricks workspace"
#   type        = string
# }

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

# variable "name" {
#   type = string
  
# }

###### Networking ########

variable "network_name" {
# Removed duplicate "region" variable; use "aws_region" instead.
  default = "dbx-net"
}

variable "azs"               { 
  type = list(string) 
  default = ["us-east-1a","us-east-1b"] 
  }
  # Optional: If you want a dedicated SG CIDR for VPC endpoints ingress (lock down from your VPC only)
variable "vpc_cidr"          { 
  type = string  
  default = "10.20.0.0/16" 
  }

# variable "public_cidrs"      {
#    type = list(string) 
#    default = ["10.20.0.0/24","10.20.1.0/24"] 
#    }
variable "private_cidrs"     { 
  type = list(string) 
  default = ["10.20.10.0/24","10.20.11.0/24"] 
  }

# # NAT: set to false if you're going 100% PrivateLink/VPC endpoints (no egress)
# variable "enable_nat_per_az" { 
#   type = bool   
#   default = true 
#   }

# ---- Databricks PrivateLink (paste from Databricks for your region) ----
# These are the *endpoint service names* that Databricks exposes in your region.
# Examples look like: "com.amazonaws.vpce.us-east-1.vpce-svc-0abc1234..." (PLACEHOLDER)

# TGW peers (optional): another VPC CIDR you’ll route to via TGW
variable "tgw_create"                      { 
  type = bool   
  default = true 
  }

variable "tgw_peer_cidr"                   {
   type = string 
   default = "10.30.0.0/16" 
   }

# Route53 Private Hosted Zone domain for Databricks PrivateLink DNS.
# You will create A/CNAME records in this zone to point to VPCE DNS names.
# See Databricks doc for exact hostnames to alias (vary by workspace).
variable "privatelink_tunnel_host"           { 
  type = string 
  default = "tunnel.privatelink.us-east-1.cloud.databricks.com" 
  }

# Attach these route tables to the S3 Gateway VPC endpoint (private subnets’ RTs)
# If you change subnet counts, module will compute the RTIDs dynamically.


variable "environment" {
  description = "Deployment environment (e.g., dev, test, prod)"
  type        = string
}

# 2) Backend host(s) -> Backend VPCE (CNAME)
# Supply the actual backend host(s) from Databricks docs/console
variable "backend_hosts" {
  type    = list(string)
  default = ["tunnel.privatelink.us-east-1.cloud.databricks.com"]
}