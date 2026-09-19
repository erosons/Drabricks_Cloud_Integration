output "resource_group_name" {
  description = "Name of the resource group created or used"
  value       = azurerm_resource_group.rg.name
}

output "databricks_workspace_url" {
  description = "URL of the deployed Databricks workspace"
  value       = azurerm_databricks_workspace.databricks.workspace_url
}

output "storage_account_name" {
  description = "Name of the storage account created"
  value       = azurerm_storage_account.storage.name
}

output "container_id" {
  description = "ID of the storage container created"
  value       = azurerm_storage_container.container.id
}
