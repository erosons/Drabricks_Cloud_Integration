###############################################################################
# outputs.tf
#
# Fully driven by var.app_registrations — no hardcoded resource references.
# Adding a new entry to var.app_registrations automatically populates all
# outputs without any changes to this file.
###############################################################################

# ── Per-app-registration summary ─────────────────────────────────────────────
# One map entry per app reg key.  Contains everything a downstream consumer
# or CI/CD pipeline needs to integrate with the registered application.

output "app_registrations" {
  description = <<-EOT
    Map of app reg key → registration summary.  One entry per key in
    var.app_registrations.  Contains client_id, identifier_uri,
    scope_uris, role_ids, and Key Vault secret names.
    Adding a new entry to var.app_registrations automatically
    populates this output — no changes to outputs.tf required.
  EOT

  value = {
    for reg_key, reg in var.app_registrations : reg_key => {

      # Core identity
      client_id      = local.all_applications[reg_key].client_id
      display_name   = local.all_applications[reg_key].display_name
      identifier_uri = reg.identifier_uri

      # Key Vault references — retrieve secrets at runtime via Managed Identity
      client_id_kv_secret_name     = azurerm_key_vault_secret.client_id[reg_key].name
      client_secret_kv_secret_name = azurerm_key_vault_secret.client_secret[reg_key].name

      # Delegated scope URIs — map of scope_value → full URI
      # e.g. { "Data.Read" = "api://my-app-abc123/Data.Read" }
      scope_uris = {
        for scope_value in keys(reg.oauth2_scopes) :
        scope_value => "${reg.identifier_uri}/${scope_value}"
        if reg.identifier_uri != null
      }

      # Delegated scope UUIDs — map of scope_value → UUID
      # Used in required_resource_access blocks of downstream app registrations.
      scope_ids = {
        for scope_value in keys(reg.oauth2_scopes) :
        scope_value => random_uuid.scope["${reg_key}:${scope_value}"].result
      }

      # App role UUIDs — map of role_value → UUID
      # Used in azuread_app_role_assignment resources.
      role_ids = {
        for role_value in keys(reg.app_roles) :
        role_value => random_uuid.role["${reg_key}:${role_value}"].result
      }
    }
  }
}

# ── Token validation config — one entry per resource server ──────────────────
# Only emitted for app regs that expose an identifier_uri (resource servers).
# Feed into auth middleware configuration at runtime.

output "token_validation_configs" {
  description = <<-EOT
    Map of app reg key → token validation settings for every app registration
    that acts as a resource server (i.e. has an identifier_uri).
    Contains authority, audience, valid_issuers, and claim names.
  EOT

  value = {
    for reg_key, reg in var.app_registrations :
    reg_key => {
      authority     = "https://login.microsoftonline.com/${var.tenant_id}/v2.0"
      audience      = reg.identifier_uri
      valid_issuers = [
        "https://sts.windows.net/${var.tenant_id}/",
        "https://login.microsoftonline.com/${var.tenant_id}/v2.0"
      ]
      # Delegated tokens (OBO): validate the 'scp' claim.
      # App-role tokens (Client Credentials): validate the 'roles' claim.
      delegated_claim = "scp"
      app_role_claim  = "roles"
    }
    if reg.identifier_uri != null
  }
}

# ── Key Vault ─────────────────────────────────────────────────────────────────

output "key_vault_uri" {
  description = "URI of the Key Vault that stores all client IDs and secrets."
  value       = azurerm_key_vault.main.vault_uri
}

output "key_vault_id" {
  description = "Resource ID of the Key Vault (used for downstream role assignments or private endpoint configuration)."
  value       = azurerm_key_vault.main.id
}
