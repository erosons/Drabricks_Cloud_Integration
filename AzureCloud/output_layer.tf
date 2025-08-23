#####################################################
### Outputs layer
#####################################################

output "resource_group_name" {
  value = var.resource_group
}

output "databrick_workspace" {
  value = azurerm_databricks_workspace.this.id
}

output keyvault_name_data {
  value = azurerm_key_vault.keyvault.id
}

output storage_account {
  value = azurerm_storage_account.this.id
}

output storage_container {
  value = azurerm_storage_container.this.id
}

output access_connector {
  value = azurerm_databricks_access_connector.this.id
}
