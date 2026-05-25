output "metastore_storage_account_id" {
  description = "ARM resource ID of the metastore storage account"
  value       = azurerm_storage_account.metastore.id
}

output "metastore_storage_account_name" {
  description = "Name of the metastore storage account"
  value       = azurerm_storage_account.metastore.name
}

output "data_storage_account_id" {
  description = "ARM resource ID of the data lake storage account (null if not created)"
  value       = try(azurerm_storage_account.data[0].id, null)
}

output "data_storage_account_name" {
  description = "Name of the data lake storage account (null if not created)"
  value       = try(azurerm_storage_account.data[0].name, null)
}

output "metastore_container_name" {
  description = "Name of the metastore container"
  value       = azurerm_storage_container.metastore.name
}
