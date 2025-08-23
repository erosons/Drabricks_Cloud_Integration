
# Creates an Azure Key Vault to securely manage secrets like the storage account keys.
resource "azurerm_key_vault" "keyvault" {
  name                        = "${var.keyvault_name}-${random_integer.number.result}"
  resource_group_name      = var.resource_group
  location                 = var.region
  enabled_for_disk_encryption = true
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days  = 7
  purge_protection_enabled    = false
  
  sku_name = "standard"
  depends_on = [ azurerm_resource_group.rg ]
}

# Access policies are set for the authenticated user to allow actions like getting and setting secrets.
resource "azurerm_key_vault_access_policy" "kv" {
    object_id = data.azurerm_client_config.current.object_id
    tenant_id = data.azurerm_client_config.current.tenant_id
    key_vault_id = azurerm_key_vault.keyvault.id

    key_permissions = [
      "Create",
      "Get",
      "List",
       "Delete",
       "Purge",
       
    ]

    secret_permissions = [
      "Set",
      "Get",
       "List",
      "Delete",
      "Purge",
      "Recover"
    ]
  }
  
  # Access policies are set for the app
resource "azurerm_key_vault_access_policy" "app_id" {
    object_id = azuread_service_principal.this.object_id
    tenant_id = data.azurerm_client_config.current.tenant_id
    key_vault_id = azurerm_key_vault.keyvault.id

    key_permissions = [
      "Create",
      "Get",
       "Delete",
       "Purge",
       
    ]

    secret_permissions = [
      "Set",
      "Get",
      "Delete",
      "Purge",
      "Recover"
    ]
   depends_on = [azuread_service_principal.this,azurerm_key_vault_access_policy.kv]
  }
  


# put the storage account key in the key vault
resource "azurerm_key_vault_secret" "app_id" {
  name         = "appid${random_integer.number.result}"
  value        = azuread_service_principal.this.client_id
  key_vault_id = azurerm_key_vault.keyvault.id

  depends_on = [azuread_service_principal.this, azurerm_key_vault.keyvault,azurerm_key_vault_access_policy.kv]
}


# put the storage account key in the key vault
resource "azurerm_key_vault_secret" "app_secret" {
  name         = "appsecret${random_integer.number.result}"
  value        = azuread_application_password.this.id
  key_vault_id = azurerm_key_vault.keyvault.id

   depends_on = [azuread_application_password.this, azurerm_key_vault.keyvault,azurerm_key_vault_access_policy.kv]
}
