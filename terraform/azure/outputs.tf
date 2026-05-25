output "workspace_url" {
  description = "Databricks workspace URL"
  value       = azurerm_databricks_workspace.main.workspace_url
}

output "workspace_id" {
  description = "Databricks workspace ID"
  value       = azurerm_databricks_workspace.main.workspace_id
}

output "workspace_resource_id" {
  description = "ARM resource ID of the Databricks workspace (use for DATABRICKS_AZURE_RESOURCE_ID)"
  value       = azurerm_databricks_workspace.main.id
}

output "metastore_storage_account_name" {
  description = "Storage account name backing the Unity Catalog metastore"
  value       = module.storage.metastore_storage_account_name
}

output "metastore_storage_account_id" {
  description = "ARM resource ID of the metastore storage account"
  value       = module.storage.metastore_storage_account_id
}

output "vnet_id" {
  description = "Virtual Network resource ID"
  value       = module.networking.vnet_id
}

output "service_principal_client_id" {
  description = "Client ID of the Databricks service principal"
  value       = azuread_application.databricks_sp.client_id
  sensitive   = true
}

output "service_principal_client_secret" {
  description = "Client secret of the Databricks service principal"
  value       = azuread_service_principal_password.databricks_sp.value
  sensitive   = true
}
