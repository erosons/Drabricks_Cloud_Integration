Terraform

Providers you’ll need:

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 3.113" }
    databricks = { source = "databricks/databricks", version = "~> 1.44" }
  }
}
provider "azurerm" { features {} }

Variables (edit to your env)
variable "prefix"             { type = string  default = "gh-dbx" }
variable "tenant_id"          { type = string }
variable "subscription_id"    { type = string }
variable "resource_group"     { type = string }
variable "location"           { type = string  default = "eastus" }
variable "databricks_ws_name" { type = string }
variable "github_org"         { type = string }
variable "github_repo"        { type = string }
# example subjects you can use:
#   repo:<org>/<repo>:environment:<env>
#   repo:<org>/<repo>:ref:refs/heads/<branch>
variable "github_subject"     { type = string  default = "" }

1) Create a User-Assigned Managed Identity + Federated Credential

In azurerm, the resource for attaching OIDC to a UAMI is
azurerm_federated_identity_credential with the UAMI’s resource_id.

# A UAMI that will represent your CI user
resource "azurerm_user_assigned_identity" "uami" {
  name                = "${var.prefix}-uami"
  resource_group_name = var.resource_group
  location            = var.location
  tags = { app = "databricks" }
}

locals {
  gh_subject = coalesce(
    var.github_subject,
    "repo:${var.github_org}/${var.github_repo}:environment:prod"
  )
}

resource "azurerm_federated_identity_credential" "github_oidc" {
  name        = "github-oidc"
  resource_id = azurerm_user_assigned_identity.uami.id  # <-- attach to UAMI
  issuer      = "https://token.actions.githubusercontent.com"
  subject     = local.gh_subject
  audiences   = ["api://AzureADTokenExchange"]
}

2) Give the UAMI the minimal roles it needs on the workspace

For quick starts, Contributor on the workspace ARM resource is fine. Tighten later.

data "azurerm_databricks_workspace" "ws" {
  name                = var.databricks_ws_name
  resource_group_name = var.resource_group
}

resource "azurerm_role_assignment" "uami_ws_contrib" {
  scope                = data.azurerm_databricks_workspace.ws.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.uami.principal_id
}

3) Tell Databricks about this identity (SCIM service principal)

A UAMI has a Client ID (an application ID). Use that to create the
Databricks service principal so permissions/entitlements can be managed inside the workspace.

# Workspace-level Databricks provider (auth however you normally do to apply TF)
provider "databricks" {
  host = "https://${var.databricks_ws_name}.azuredatabricks.net"
}

# Create a Databricks Service Principal mapped to the UAMI's Client ID
resource "databricks_service_principal" "ci" {
  application_id = azurerm_user_assigned_identity.uami.client_id
  display_name   = "${var.prefix}-uami"
}

# Grant common entitlements (adjust to your needs)
resource "databricks_entitlements" "ci" {
  service_principal_id = databricks_service_principal.ci.id
  allow_cluster_create = true
  workspace_access     = true
}

# Example: scope permissions, cluster policies, job permissions, etc., go here…
# resource "databricks_permissions" "jobs" { ... }
