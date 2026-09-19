# =============================================================================
# AUTHENTICATION
# =============================================================================

variable "azure_subscription_id" {
  description = "Azure subscription ID"
  type        = string
  sensitive   = true
}

variable "azure_tenant_id" {
  description = "Azure Active Directory tenant ID"
  type        = string
  sensitive   = true
}

variable "azure_client_id" {
  description = "Service principal client ID used by Terraform"
  type        = string
  sensitive   = true
}

variable "azure_client_secret" {
  description = "Service principal client secret used by Terraform"
  type        = string
  sensitive   = true
}

# =============================================================================
# GENERAL
# =============================================================================

variable "environment" {
  description = "Deployment environment (prod, staging, dev)"
  type        = string
  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "environment must be prod, staging, or dev."
  }
}

variable "project_name" {
  description = "Project name used in resource naming"
  type        = string
}

variable "location" {
  description = "Azure region for all resources"
  type        = string
  default     = "eastus"
}

variable "common_tags" {
  description = "Tags applied to every resource"
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Project   = "Databricks"
  }
}

# =============================================================================
# DATABRICKS WORKSPACE
# =============================================================================

variable "databricks_sku" {
  description = "Databricks workspace SKU (standard, premium, trial)"
  type        = string
  default     = "premium"
}

variable "default_catalog_name" {
  description = "Default Unity Catalog catalog assigned to the workspace"
  type        = string
  default     = "main"
}

# =============================================================================
# NETWORKING
# =============================================================================

variable "vnet_address_space" {
  description = "Address space for the VNet"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "public_subnet_prefix" {
  description = "CIDR for the public (Databricks) subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "private_subnet_prefix" {
  description = "CIDR for the private subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "enable_private_endpoints" {
  description = "Deploy private endpoints for storage and other services"
  type        = bool
  default     = true
}

# =============================================================================
# STORAGE
# =============================================================================

variable "storage_replication_type" {
  description = "Storage account replication type (LRS, GRS, RAGRS, ZRS)"
  type        = string
  default     = "GRS"
}

variable "storage_access_tier" {
  description = "Storage account access tier (Hot, Cool)"
  type        = string
  default     = "Hot"
}

variable "enable_blob_versioning" {
  description = "Enable blob versioning on storage accounts"
  type        = bool
  default     = true
}

variable "enable_last_access_time" {
  description = "Enable last-access-time tracking on storage accounts"
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
  description = "Create a dedicated ADLS Gen2 account for the data lake"
  type        = bool
  default     = false
}

variable "enable_cmk" {
  description = "Encrypt storage with Customer Managed Keys"
  type        = bool
  default     = false
}

variable "metastore_container_name" {
  description = "Container name for the Unity Catalog metastore"
  type        = string
  default     = "metastore"
}

variable "data_container_name" {
  description = "Container name for data"
  type        = string
  default     = "data"
}

# =============================================================================
# CLUSTER POLICIES — PRODUCTION
# =============================================================================

variable "create_prod_policy" {
  description = "Create the production cluster policy"
  type        = bool
  default     = true
}

variable "prod_spark_version" {
  type    = string
  default = "14.3.x-scala2.12"
}

variable "prod_driver_node_type" {
  type    = string
  default = "Standard_DS4_v2"
}

variable "prod_worker_node_type" {
  type    = string
  default = "Standard_DS4_v2"
}

variable "prod_allowed_worker_types" {
  type    = list(string)
  default = ["Standard_DS4_v2", "Standard_DS5_v2"]
}

variable "prod_num_workers" {
  type    = number
  default = 4
}

variable "prod_worker_range" {
  description = "[min, max] worker count for production clusters"
  type        = list(number)
  default     = [2, 8]
}

variable "prod_autotermination_minutes" {
  type    = number
  default = 60
}

variable "prod_autotermination_range" {
  description = "[min, max] autotermination minutes for production clusters"
  type        = list(number)
  default     = [30, 120]
}

variable "prod_spark_conf" {
  type    = map(string)
  default = {}
}

variable "prod_init_scripts_path" {
  type    = string
  default = "dbfs:/init-scripts/prod"
}

variable "prod_log_path" {
  type    = string
  default = "dbfs:/cluster-logs/prod"
}

# =============================================================================
# CLUSTER POLICIES — STAGING
# =============================================================================

variable "create_staging_policy" {
  type    = bool
  default = true
}

variable "staging_spark_version" {
  type    = string
  default = "14.3.x-scala2.12"
}

variable "staging_driver_node_type" {
  type    = string
  default = "Standard_DS3_v2"
}

variable "staging_worker_node_type" {
  type    = string
  default = "Standard_DS3_v2"
}

variable "staging_allowed_worker_types" {
  type    = list(string)
  default = ["Standard_DS3_v2", "Standard_DS4_v2"]
}

variable "staging_num_workers" {
  type    = number
  default = 2
}

variable "staging_worker_range" {
  type    = list(number)
  default = [1, 4]
}

variable "staging_autotermination_minutes" {
  type    = number
  default = 30
}

variable "staging_autotermination_range" {
  type    = list(number)
  default = [15, 60]
}

variable "staging_spark_conf" {
  type    = map(string)
  default = {}
}

# =============================================================================
# CLUSTER POLICIES — DEVELOPMENT
# =============================================================================

variable "create_dev_policy" {
  type    = bool
  default = true
}

variable "dev_spark_version" {
  type    = string
  default = "14.3.x-scala2.12"
}

variable "dev_driver_node_type" {
  type    = string
  default = "Standard_DS3_v2"
}

variable "dev_worker_node_type" {
  type    = string
  default = "Standard_DS3_v2"
}

variable "dev_allowed_worker_types" {
  type    = list(string)
  default = ["Standard_DS3_v2", "Standard_DS4_v2", "Standard_F4s_v2"]
}

variable "dev_num_workers" {
  type    = number
  default = 1
}

variable "dev_worker_range" {
  type    = list(number)
  default = [0, 4]
}

variable "dev_autotermination_minutes" {
  type    = number
  default = 20
}

variable "dev_autotermination_range" {
  type    = list(number)
  default = [10, 60]
}

# =============================================================================
# CLUSTER POLICIES — SQL WAREHOUSE
# =============================================================================

variable "create_sql_warehouse_policy" {
  type    = bool
  default = true
}

variable "warehouse_spark_version" {
  type    = string
  default = "14.3.x-scala2.12"
}

variable "warehouse_driver_node_type" {
  type    = string
  default = "Standard_DS4_v2"
}

variable "warehouse_num_workers" {
  type    = number
  default = 2
}

variable "warehouse_worker_range" {
  type    = list(number)
  default = [1, 6]
}

variable "warehouse_autotermination_minutes" {
  type    = number
  default = 30
}

variable "warehouse_autotermination_range" {
  type    = list(number)
  default = [10, 60]
}

variable "warehouse_spark_conf" {
  type    = map(string)
  default = {}
}

# =============================================================================
# CLUSTER POLICIES — INTERACTIVE
# =============================================================================

variable "create_interactive_policy" {
  type    = bool
  default = true
}

variable "interactive_spark_version" {
  type    = string
  default = "14.3.x-scala2.12"
}

variable "interactive_driver_node_type" {
  type    = string
  default = "Standard_DS3_v2"
}

variable "interactive_worker_node_type" {
  type    = string
  default = "Standard_DS3_v2"
}

variable "interactive_num_workers" {
  type    = number
  default = 2
}

variable "interactive_worker_range" {
  type    = list(number)
  default = [1, 4]
}

variable "interactive_autotermination_minutes" {
  type    = number
  default = 30
}

variable "interactive_autotermination_range" {
  type    = list(number)
  default = [15, 60]
}

# =============================================================================
# CLUSTER POLICIES — JOB
# =============================================================================

variable "create_job_policy" {
  type    = bool
  default = true
}

variable "job_spark_version" {
  type    = string
  default = "14.3.x-scala2.12"
}

variable "job_driver_node_type" {
  type    = string
  default = "Standard_DS4_v2"
}

variable "job_worker_node_type" {
  type    = string
  default = "Standard_DS4_v2"
}

variable "job_num_workers" {
  type    = number
  default = 4
}
