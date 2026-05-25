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

variable "vnet_address_space" {
  description = "Address space for the VNet"
  type        = list(string)
  default     = ["10.0.0.0/16"]
}

variable "public_subnet_prefix" {
  description = "Address prefix for public subnet"
  type        = string
  default     = "10.0.0.0/24"
}

variable "private_subnet_prefix" {
  description = "Address prefix for private subnet"
  type        = string
  default     = "10.0.1.0/24"
}

variable "enable_private_endpoints" {
  description = "Enable Private Endpoints for secure connectivity"
  type        = bool
  default     = true
}

variable "common_tags" {
  description = "Common tags to apply to all resources"
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
    Project   = "Databricks"
  }
}
