###############################################################################
# main.tf
# Data sources and shared locals.
# Provider configuration lives in provider.tf.
# All app-registration resource logic lives in app_registrations.tf.
###############################################################################

###############################################################################
# Data sources
###############################################################################

data "azuread_client_config" "current" {}

data "azurerm_resource_group" "main" {
  name = var.resource_group_name
}

###############################################################################
# Shared locals
###############################################################################

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

locals {
  # Stable 6-char suffix appended to resource names that must be globally
  # unique (Key Vault name, future storage accounts, etc.).
  name_suffix = random_string.suffix.result

  # Base tag map merged onto every Azure resource.
  common_tags = merge(
    var.tags,
    {
      project    = var.project_name
      managed_by = "terraform"
    }
  )
}
