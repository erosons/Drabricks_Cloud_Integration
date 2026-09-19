locals {
  # Concatenate variables for resource names
  storage_account_full_name = "${var.storage_account_name}${random_string.suffix.result}"
  
  # Apply a regex to remove non-alphanumeric characters from resource group name
  sanitized_resource_group_name = regex("^[a-zA-Z0-9]+$", var.resource_group_name)
}
