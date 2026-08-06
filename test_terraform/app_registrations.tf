###############################################################################
# app_registrations.tf
#
# Two-phase app registration pattern to avoid Terraform dependency cycles:
#
#   PHASE 1 — resource_server apps  (azuread_application.resource_server)
#     Apps that only EXPOSE APIs.  No cross-app references in their HCL.
#     Must exist before client apps are created.
#     Example: data_api
#
#   PHASE 2 — client apps  (azuread_application.client)
#     Apps that CONSUME other APIs via required_resource_access.
#     Reference resource_server apps by key.
#     Examples: daemon_client, middle_tier
#
# Why the split?
#   required_resource_access inside a single for_each block creates
#   cross-instance references (daemon_client → data_api).  Combined with
#   azuread_application_pre_authorized modifying data_api's manifest,
#   Terraform's graph sees a destroy-path cycle across all three instances.
#   Separate resource blocks make the layer boundary explicit and the graph
#   stays acyclic in both create and destroy directions.
#
# Resource address anatomy:
#   random_uuid.scope["<reg_key>:<scope_value>"]
#   random_uuid.role["<reg_key>:<role_value>"]
#   azuread_application.resource_server["<reg_key>"]   — e.g. data_api
#   azuread_application.client["<reg_key>"]            — e.g. daemon_client, middle_tier
#   azuread_service_principal.this["<reg_key>"]
#   azuread_application_password.this["<reg_key>"]
#   azuread_app_role_assignment.this["<reg_key>:<role_value>"]
#   azuread_application_pre_authorized.this["<reg_key>"]
###############################################################################

###############################################################################
# Locals
###############################################################################

locals {
  # Apps that only expose APIs — no required_resource_access cross-references.
  resource_server_regs = {
    for k, v in var.app_registrations : k => v
    if v.client_credential_access == null && v.obo_access == null
  }

  # Apps that consume other APIs — have required_resource_access.
  client_regs = {
    for k, v in var.app_registrations : k => v
    if v.client_credential_access != null || v.obo_access != null
  }

  # Merged lookup map — used by service principals, passwords, KV secrets,
  # and outputs so they don't need to know which resource block an app is in.
  all_applications = merge(
    { for k, v in azuread_application.resource_server : k => v },
    { for k, v in azuread_application.client : k => v }
  )

  # Flatten all oauth2 scopes across every app reg into a single map.
  # Key format: "<reg_key>:<scope_value>"  e.g. "data_api:Data.Read"
  all_scopes = merge([
    for reg_key, reg in var.app_registrations : {
      for scope_value, _ in reg.oauth2_scopes :
      "${reg_key}:${scope_value}" => {
        reg_key     = reg_key
        scope_value = scope_value
      }
    }
  ]...)

  # Flatten all app roles across every app reg into a single map.
  # Key format: "<reg_key>:<role_value>"  e.g. "data_api:DataReader"
  all_roles = merge([
    for reg_key, reg in var.app_registrations : {
      for role_value, _ in reg.app_roles :
      "${reg_key}:${role_value}" => {
        reg_key    = reg_key
        role_value = role_value
      }
    }
  ]...)

  # Flatten all client_credential role assignments into a single map.
  # Key format: "<reg_key>:<role_value>"  e.g. "daemon_client:DataReader"
  all_cc_assignments = merge([
    for reg_key, reg in var.app_registrations :
    reg.client_credential_access != null ? {
      for role_value in reg.client_credential_access.assigned_roles :
      "${reg_key}:${role_value}" => {
        client_reg_key = reg_key
        target_reg_key = reg.client_credential_access.target_app_reg_key
        role_value     = role_value
      }
    } : {}
  ]...)
}

###############################################################################
# UUID generation — layer 1, no resource dependencies
# Compound key "<reg_key>:<value>" ensures each scope/role across ALL app
# registrations gets its own stable UUID.  Never rename a key or value.
###############################################################################

resource "random_uuid" "scope" {
  for_each = local.all_scopes
}

resource "random_uuid" "role" {
  for_each = local.all_roles
}

###############################################################################
# PHASE 1 — Resource server app registrations
# These apps only expose APIs.  No cross-app references here so Terraform
# can create them before any client app exists.
###############################################################################

resource "azuread_application" "resource_server" {
  for_each = local.resource_server_regs

  display_name     = each.value.display_name
  sign_in_audience = coalesce(each.value.sign_in_audience, "AzureADMyOrg")
  identifier_uris  = each.value.identifier_uri != null ? [each.value.identifier_uri] : []
  owners           = [data.azuread_client_config.current.object_id]

  dynamic "web" {
    for_each = each.value.homepage_url != null ? [each.value.homepage_url] : []
    content {
      homepage_url = web.value
    }
  }

  dynamic "api" {
    for_each = (
      length(each.value.oauth2_scopes) > 0 ||
      each.value.identifier_uri != null
    ) ? [1] : []

    content {
      requested_access_token_version = 2

      dynamic "oauth2_permission_scope" {
        for_each = each.value.oauth2_scopes

        content {
          id                         = random_uuid.scope["${each.key}:${oauth2_permission_scope.key}"].result
          value                      = oauth2_permission_scope.key
          type                       = oauth2_permission_scope.value.type
          enabled                    = oauth2_permission_scope.value.enabled
          admin_consent_display_name = oauth2_permission_scope.value.admin_consent_display_name
          admin_consent_description  = oauth2_permission_scope.value.admin_consent_description
          user_consent_display_name  = oauth2_permission_scope.value.user_consent_display_name
          user_consent_description   = oauth2_permission_scope.value.user_consent_description
        }
      }
    }
  }

  dynamic "app_role" {
    for_each = each.value.app_roles

    content {
      id                   = random_uuid.role["${each.key}:${app_role.key}"].result
      value                = app_role.key
      display_name         = app_role.value.display_name
      description          = app_role.value.description
      allowed_member_types = app_role.value.allowed_member_types
      enabled              = app_role.value.enabled
    }
  }

  # Ensure the 'roles' claim is present in tokens for apps that expose app roles.
  # Azure AD emits 'scp' automatically for v2 delegated tokens — no optional_claims needed.
  dynamic "optional_claims" {
    for_each = length(each.value.app_roles) > 0 ? [1] : []
    content {
      access_token { name = "roles" }
      id_token     { name = "roles" }
    }
  }

  tags = [each.key, var.project_name]
}

###############################################################################
# PHASE 2 — Client app registrations
# These apps consume other APIs.  required_resource_access references
# azuread_application.resource_server so the dependency is cross-resource
# (not cross-instance), which Terraform resolves cleanly.
###############################################################################

resource "azuread_application" "client" {
  for_each = local.client_regs

  display_name     = each.value.display_name
  sign_in_audience = coalesce(each.value.sign_in_audience, "AzureADMyOrg")
  identifier_uris  = each.value.identifier_uri != null ? [each.value.identifier_uri] : []
  owners           = [data.azuread_client_config.current.object_id]

  dynamic "web" {
    for_each = each.value.homepage_url != null ? [each.value.homepage_url] : []
    content {
      homepage_url = web.value
    }
  }

  dynamic "api" {
    for_each = (
      length(each.value.oauth2_scopes) > 0 ||
      each.value.obo_access != null ||
      each.value.identifier_uri != null
    ) ? [1] : []

    content {
      requested_access_token_version = 2

      dynamic "oauth2_permission_scope" {
        for_each = each.value.oauth2_scopes

        content {
          id                         = random_uuid.scope["${each.key}:${oauth2_permission_scope.key}"].result
          value                      = oauth2_permission_scope.key
          type                       = oauth2_permission_scope.value.type
          enabled                    = oauth2_permission_scope.value.enabled
          admin_consent_display_name = oauth2_permission_scope.value.admin_consent_display_name
          admin_consent_description  = oauth2_permission_scope.value.admin_consent_description
          user_consent_display_name  = oauth2_permission_scope.value.user_consent_display_name
          user_consent_description   = oauth2_permission_scope.value.user_consent_description
        }
      }
    }
  }

  dynamic "app_role" {
    for_each = each.value.app_roles

    content {
      id                   = random_uuid.role["${each.key}:${app_role.key}"].result
      value                = app_role.key
      display_name         = app_role.value.display_name
      description          = app_role.value.description
      allowed_member_types = app_role.value.allowed_member_types
      enabled              = app_role.value.enabled
    }
  }

  dynamic "optional_claims" {
    for_each = length(each.value.app_roles) > 0 ? [1] : []
    content {
      access_token { name = "roles" }
      id_token     { name = "roles" }
    }
  }

  # Client Credentials — reference the resource server by its resource block.
  dynamic "required_resource_access" {
    for_each = each.value.client_credential_access != null ? [each.value.client_credential_access] : []

    content {
      resource_app_id = azuread_application.resource_server[required_resource_access.value.target_app_reg_key].client_id

      dynamic "resource_access" {
        for_each = required_resource_access.value.assigned_roles

        content {
          id   = random_uuid.role["${required_resource_access.value.target_app_reg_key}:${resource_access.value}"].result
          type = "Role"
        }
      }
    }
  }

  # OBO — reference the resource server by its resource block.
  dynamic "required_resource_access" {
    for_each = each.value.obo_access != null ? [each.value.obo_access] : []

    content {
      resource_app_id = azuread_application.resource_server[required_resource_access.value.target_app_reg_key].client_id

      dynamic "resource_access" {
        for_each = required_resource_access.value.requested_scopes

        content {
          id   = random_uuid.scope["${required_resource_access.value.target_app_reg_key}:${resource_access.value}"].result
          type = "Scope"
        }
      }
    }
  }

  tags = [each.key, var.project_name]
}

###############################################################################
# Service principals — one per app registration
###############################################################################

resource "azuread_service_principal" "this" {
  for_each = var.app_registrations

  client_id                    = local.all_applications[each.key].client_id
  app_role_assignment_required = each.value.require_role_assignment
  owners                       = [data.azuread_client_config.current.object_id]
}

###############################################################################
# Client secrets — one per app registration, stored in Key Vault
###############################################################################

resource "azuread_application_password" "this" {
  for_each = var.app_registrations

  application_id = local.all_applications[each.key].id
  display_name   = "${each.key}-secret"
  end_date       = each.value.secret_expiry
}

resource "azurerm_key_vault_secret" "client_id" {
  for_each = var.app_registrations

  name         = "${replace(each.key, "_", "-")}-client-id"
  value        = local.all_applications[each.key].client_id
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.kv_terraform_secrets_officer]

  tags = local.common_tags
}

resource "azurerm_key_vault_secret" "client_secret" {
  for_each = var.app_registrations

  name         = "${replace(each.key, "_", "-")}-client-secret"
  value        = azuread_application_password.this[each.key].value
  key_vault_id = azurerm_key_vault.main.id

  depends_on = [azurerm_role_assignment.kv_terraform_secrets_officer]

  tags = local.common_tags
}

###############################################################################
# App role assignments — admin consent for Client Credentials callers
###############################################################################

resource "azuread_app_role_assignment" "this" {
  for_each = local.all_cc_assignments

  app_role_id         = random_uuid.role["${each.value.target_reg_key}:${each.value.role_value}"].result
  principal_object_id = azuread_service_principal.this[each.value.client_reg_key].object_id
  resource_object_id  = azuread_service_principal.this[each.value.target_reg_key].object_id
}

###############################################################################
# Pre-authorization — suppress consent prompts for OBO callers
###############################################################################

resource "azuread_application_pre_authorized" "this" {
  for_each = {
    for reg_key, reg in var.app_registrations :
    reg_key => reg.obo_access
    if try(reg.obo_access.pre_authorize, false)
  }

  application_id       = azuread_application.resource_server[each.value.target_app_reg_key].id
  authorized_client_id = azuread_application.client[each.key].client_id
  permission_ids = [
    for scope_value in each.value.requested_scopes :
    random_uuid.scope["${each.value.target_app_reg_key}:${scope_value}"].result
  ]
}
