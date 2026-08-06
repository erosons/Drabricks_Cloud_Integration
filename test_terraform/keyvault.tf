###############################################################################
# keyvault.tf
# RBAC-enabled Key Vault.
#
# Client ID and client secret for every app registration are written here by
# app_registrations.tf via azurerm_key_vault_secret.client_id/client_secret.
# This file owns only the vault itself and its access grants.
###############################################################################

resource "azurerm_key_vault" "main" {
  name                          = "kv-${substr(var.project_name, 0, 12)}-${local.name_suffix}"
  location                      = data.azurerm_resource_group.main.location
  resource_group_name           = data.azurerm_resource_group.main.name
  tenant_id                     = var.tenant_id
  sku_name                      = "standard"
  purge_protection_enabled      = true
  soft_delete_retention_days    = 90
  enable_rbac_authorization     = true
  public_network_access_enabled = var.keyvault_public_network_access_enabled

  network_acls {
    bypass         = "AzureServices"
    default_action = var.keyvault_public_network_access_enabled ? "Allow" : "Deny"
    ip_rules       = var.keyvault_allowed_ip_cidrs
  }

  tags = local.common_tags
}

# ── Terraform SPN — write secrets during apply ────────────────────────────────

resource "azurerm_role_assignment" "kv_terraform_secrets_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azuread_client_config.current.object_id
}

# ── Workload Managed Identities — read secrets at runtime ────────────────────
# for_each over a set of principal IDs = stable resource addresses.

resource "azurerm_role_assignment" "kv_workload_secrets_user" {
  for_each = toset(var.keyvault_workload_principal_ids)

  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = each.value
}

# ── App registrations — Key Vault Secrets User for all registered SPNs ───────
# Every app reg in var.app_registrations gets read access to KV secrets so it
# can retrieve its own client-id / client-secret at runtime.

resource "azurerm_role_assignment" "kv_app_reg_secrets_user" {
  for_each = var.app_registrations

  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azuread_service_principal.this[each.key].object_id
}

# ── kv_key_service — Key Vault Crypto Officer for key read/write ──────────────
# Additional role for the dedicated key-management service principal.

resource "azurerm_role_assignment" "kv_key_service_crypto_officer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Crypto Officer"
  principal_id         = azuread_service_principal.this["kv_key_service"].object_id
}
