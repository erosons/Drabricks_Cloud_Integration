
variable "tags" {
  type        = map(string)
  description = "Additional tags applied to all resources created"
  default     = {}
}

variable "resource_group" {
  type        = string
  description = "Name of the Azure Resource Group"
  
}

variable "region" {
  type        = string
  description = "Azure region where resources will be created"
}

variable workspace_name  {
  type        = string
  description = "Name of the Databricks workspace"
}

variable "dbx_access_connetor" {
  description = "Databricks access connector name"
  type        = string
}

variable "container_name" {
  description = "Name of the storage container for Unity Catalog"
  type        = string
}

variable subscription_id {
  description = "Azure subscription ID"
  type        = string
}

variable "secret_scope_name" {
  description = "Name of the secret scope to create in Databricks"
  type        = string
  
}

variable "keyvault_name" {
  description = "Name of the Azure Key Vault to create"
  type        = string
}

variable "app_name" {
  description = "Name of the application to create in Azure AD"
  type        = string
}

variable "app_secret_name" {
  description = "Name of the application secret to create in Azure AD"
  type        = string
}

variable "sku_value" {
  description = "SKU value for the Databricks workspace"
  type        = string
  default     = "premium"
}

variable "storage_account_name" {
  description = "Name of the storage account to create"
  type        = string
}