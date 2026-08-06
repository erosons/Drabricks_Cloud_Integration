###############################################################################
# variables.tf
# SCHEMA DEFINITIONS ONLY — no default values.
# All values live in environment tfvars files (e.g. dev.environment.tfvars).
#
# Block ordering per terraform-skill:
#   description → type → validation → nullable
###############################################################################

# ── Platform identity ─────────────────────────────────────────────────────────

variable "subscription_id" {
  description = "Azure subscription ID that hosts the Key Vault and resource group."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$", var.subscription_id))
    error_message = "subscription_id must be a valid lowercase UUID."
  }
}

variable "tenant_id" {
  description = "Azure AD (Entra ID) tenant ID. Used as the token issuer authority in all generated outputs."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$", var.tenant_id))
    error_message = "tenant_id must be a valid lowercase UUID."
  }
}

# ── Resource placement ────────────────────────────────────────────────────────

variable "resource_group_name" {
  description = "Name of an existing Azure resource group where the Key Vault will be created."
  type        = string
  nullable    = false
}

variable "project_name" {
  description = "Short project identifier used as a name prefix for all Azure and Entra ID resources. Lowercase alphanumeric and hyphens only, 3–40 characters."
  type        = string
  nullable    = false

  validation {
    condition     = can(regex("^[a-z0-9-]{3,40}$", var.project_name))
    error_message = "project_name must be 3–40 lowercase alphanumeric characters or hyphens."
  }
}

# ── Key Vault network ─────────────────────────────────────────────────────────

variable "keyvault_public_network_access_enabled" {
  description = "Allow public internet access to the Key Vault. Set false in production and pair with a private endpoint."
  type        = bool
  nullable    = false
}

variable "keyvault_allowed_ip_cidrs" {
  description = "List of IPv4 CIDR blocks permitted through the Key Vault firewall when public access is enabled."
  type        = list(string)
  nullable    = false

  validation {
    condition = alltrue([
      for cidr in var.keyvault_allowed_ip_cidrs : can(cidrhost(cidr, 0))
    ])
    error_message = "Every entry must be a valid CIDR block, e.g. '203.0.113.0/24'."
  }
}

variable "keyvault_workload_principal_ids" {
  description = "Object IDs of Managed Identities that need Key Vault Secrets User access to read secrets at runtime (e.g. Databricks cluster MSI)."
  type        = list(string)
  nullable    = false

  validation {
    condition = alltrue([
      for id in var.keyvault_workload_principal_ids :
      can(regex("^[0-9a-f]{8}-([0-9a-f]{4}-){3}[0-9a-f]{12}$", id))
    ])
    error_message = "Every entry must be a valid lowercase UUID."
  }
}

# ── Tags ──────────────────────────────────────────────────────────────────────

variable "tags" {
  description = "Base tags merged onto every resource. The keys 'project' and 'managed_by' are always added automatically."
  type        = map(string)
  nullable    = false
}

###############################################################################
# App registration schema
#
# var.app_registrations is the single source of truth for all Entra ID app
# registrations provisioned by this module.  Each map entry creates:
#   • one azuread_application  (the app reg itself)
#   • one azuread_service_principal
#   • one azuread_application_password  (stored in Key Vault)
#   • N random_uuid resources — one per oauth2 scope, one per app role
#   • optional azuread_app_role_assignment resources  (for client_credential clients)
#   • optional azuread_application_pre_authorized     (for obo clients)
#
# Map key = stable logical name (e.g. "data_api", "daemon_client").
# NEVER rename a map key after first apply — the UUID resources are addressed
# by this key and renaming causes destroy/recreate of all child resources.
#
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  oauth2_scope schema  (map key = scope value string, e.g. "Data.Read") │
# │    type                       string  "User" | "Admin"                  │
# │    enabled                    bool                                      │
# │    admin_consent_display_name string                                    │
# │    admin_consent_description  string                                    │
# │    user_consent_display_name  string                                    │
# │    user_consent_description   string                                    │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  app_role schema  (map key = role value string, e.g. "DataReader")     │
# │    display_name         string                                          │
# │    description          string                                          │
# │    allowed_member_types list(string)  ["Application"] | ["User"] | both│
# │    enabled              bool                                            │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  client_credential_access  (for daemon / service-principal callers)    │
# │    target_app_reg_key  string   key of the resource-server app reg     │
# │    assigned_roles      set(string)  role value strings to assign       │
# ├─────────────────────────────────────────────────────────────────────────┤
# │  obo_access  (for middle-tier / on-behalf-of callers)                  │
# │    target_app_reg_key   string      key of the downstream resource app │
# │    requested_scopes     set(string) scope values to request via OBO    │
# │    pre_authorize        bool        suppress user consent prompt        │
# └─────────────────────────────────────────────────────────────────────────┘
###############################################################################

variable "app_registrations" {
  description = <<-EOT
    Map of Entra ID app registrations to provision.  Map key is a stable
    logical name (e.g. "data_api") used as a resource address prefix —
    never rename a key after first apply.

    Each entry configures one complete app registration including its
    scopes, app roles, and any downstream access grants (OBO or
    Client Credentials).  To add a new app registration, add a new
    entry to this map in the environment tfvars file.
  EOT

  type = map(object({

    # ── App registration identity ───────────────────────────────────────────
    display_name     = string           # shown in Azure portal & consent prompts
    identifier_uri   = optional(string) # e.g. "api://my-app"; null = no URI (public clients)
    homepage_url     = optional(string) # Databricks Apps / SPA URL; null = omit web block
    sign_in_audience = optional(string) # "AzureADMyOrg" (default) | "AzureADMultipleOrgs"
    secret_expiry    = string           # ISO 8601 UTC, e.g. "2027-01-01T00:00:00Z"

    # ── Permissions this app EXPOSES (resource server) ──────────────────────
    # Delegated scopes — used by OBO callers; map key = scope value string.
    oauth2_scopes = optional(map(object({
      type                       = string # "User" | "Admin"
      enabled                    = bool
      admin_consent_display_name = string
      admin_consent_description  = string
      user_consent_display_name  = string
      user_consent_description   = string
    })), {})

    # App roles — used by Client Credentials callers; map key = role value string.
    app_roles = optional(map(object({
      display_name         = string
      description          = string
      allowed_member_types = list(string)
      enabled              = bool
    })), {})

    # ── Token assignment behaviour ──────────────────────────────────────────
    # true = only explicitly assigned SPNs can get tokens (recommended for prod)
    require_role_assignment = optional(bool, true)

    # ── Access grants this app RECEIVES (client) ────────────────────────────
    # Populate when this app calls another resource server.

    # Client Credentials grant — machine-to-machine, no user context.
    # target_app_reg_key must be a key present in var.app_registrations.
    client_credential_access = optional(object({
      target_app_reg_key = string
      assigned_roles     = set(string)
    }), null)

    # OBO grant — caller holds a user token and exchanges it downstream.
    obo_access = optional(object({
      target_app_reg_key = string
      requested_scopes   = set(string)
      pre_authorize      = bool # when true, suppresses user consent prompt
    }), null)

  }))

  nullable = false

  # ── Scope type validation ─────────────────────────────────────────────────
  validation {
    condition = alltrue(flatten([
      for reg_key, reg in var.app_registrations : [
        for scope_key, scope in reg.oauth2_scopes :
        contains(["User", "Admin"], scope.type)
      ]
    ]))
    error_message = "Every oauth2_scope.type must be 'User' or 'Admin'."
  }

  # ── App role must have at least one member type ───────────────────────────
  validation {
    condition = alltrue(flatten([
      for reg_key, reg in var.app_registrations : [
        for role_key, role in reg.app_roles :
        length(role.allowed_member_types) > 0
      ]
    ]))
    error_message = "Every app_role must have at least one allowed_member_type."
  }

  # ── Secret expiry format ──────────────────────────────────────────────────
  validation {
    condition = alltrue([
      for reg_key, reg in var.app_registrations :
      can(regex("^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$", reg.secret_expiry))
    ])
    error_message = "Every secret_expiry must be ISO 8601 UTC format: YYYY-MM-DDTHH:MM:SSZ."
  }

  # ── Homepage URL must be HTTPS when provided ──────────────────────────────
  validation {
    condition = alltrue([
      for reg_key, reg in var.app_registrations :
      reg.homepage_url == null || can(regex("^https://", reg.homepage_url))
    ])
    error_message = "When provided, homepage_url must be an HTTPS URL."
  }

  # ── sign_in_audience must be a recognised value ───────────────────────────
  validation {
    condition = alltrue([
      for reg_key, reg in var.app_registrations :
      reg.sign_in_audience == null ||
      contains(["AzureADMyOrg", "AzureADMultipleOrgs", "AzureADandPersonalMicrosoftAccount"], reg.sign_in_audience)
    ])
    error_message = "sign_in_audience must be AzureADMyOrg, AzureADMultipleOrgs, or AzureADandPersonalMicrosoftAccount."
  }
}
