variable "environment" {
  description = "Environment name (prod, staging, dev)"
  type        = string
  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "Environment must be prod, staging, or dev."
  }
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
}

variable "location" {
  description = "Azure region for resources"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
}

variable "storage_replication_type" {
  description = "Replication type for storage accounts (LRS, GRS, RAGRS, ZRS)"
  type        = string
  default     = "GRS"
}

variable "storage_access_tier" {
  description = "Access tier for storage accounts (Hot, Cool)"
  type        = string
  default     = "Hot"
}

variable "enable_blob_versioning" {
  description = "Enable blob versioning"
  type        = bool
  default     = true
}

variable "enable_last_access_time" {
  description = "Enable last access time tracking"
  type        = bool
  default     = true
}

variable "blob_delete_retention_days" {
  description = "Soft-delete retention days for blobs"
  type        = number
  default     = 7
}

variable "container_delete_retention_days" {
  description = "Soft-delete retention days for containers"
  type        = number
  default     = 7
}

variable "create_separate_data_storage" {
  description = "Create a separate ADLS Gen2 storage account for the data lake"
  type        = bool
  default     = false
}

variable "allowed_subnet_ids" {
  description = "Subnet IDs allowed to access storage accounts via service endpoints"
  type        = list(string)
}

variable "enable_private_endpoints" {
  description = "Enable Private Endpoints for storage accounts"
  type        = bool
  default     = true
}

variable "private_subnet_id" {
  description = "ID of the private subnet where private endpoints are deployed"
  type        = string
}

variable "blob_private_dns_zone_name" {
  description = "Name of the private DNS zone for blob storage (e.g. privatelink.blob.core.windows.net)"
  type        = string
  default     = null
}

variable "metastore_container_name" {
  description = "Name for the Unity Catalog metastore container"
  type        = string
  default     = "metastore"
}

variable "data_container_name" {
  description = "Name for the data container"
  type        = string
  default     = "data"
}

variable "enable_cmk" {
  description = "Enable Customer Managed Keys for storage encryption"
  type        = bool
  default     = false
}

variable "key_vault_id" {
  description = "Key Vault resource ID for CMK (required when enable_cmk = true)"
  type        = string
  default     = null
}

variable "key_vault_key_name" {
  description = "Key Vault key name for CMK (required when enable_cmk = true)"
  type        = string
  default     = null
}

variable "key_vault_key_version" {
  description = "Key Vault key version for CMK (required when enable_cmk = true)"
  type        = string
  default     = null
}

variable "user_assigned_identity_id" {
  description = "User-assigned identity resource ID for CMK (required when enable_cmk = true)"
  type        = string
  default     = null
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Project   = "Databricks"
  }
}
