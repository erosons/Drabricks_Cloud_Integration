variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "example-rg"
}

variable "location" {
  description = "Azure region for resources"
  type        = string
  default     = "East US"
}

variable "databricks_workspace_name" {
  description = "Name of the Databricks workspace"
  type        = string
  default     = "example-databricks-workspace"
}

variable "storage_account_name" {
  description = "Name of the storage account"
  type        = string
  default     = "examplestorageacct"
}

variable "container_name" {
  description = "Name of the storage container"
  type        = string
  default     = "example-container"
}
