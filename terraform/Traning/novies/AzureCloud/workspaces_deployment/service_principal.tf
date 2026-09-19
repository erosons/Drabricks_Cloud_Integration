# 1. Register App in AAD

data "azuread_client_config" "current" {}

resource "azuread_application_registration" "this" {
  display_name = "${var.app_name}-${random_integer.number.result}"

}

resource "azuread_service_principal" "this" {
  client_id                    = azuread_application_registration.this.client_id
  app_role_assignment_required = true
  owners                       = [data.azuread_client_config.current.object_id]
}

# 3. Create Client Secret
resource "azuread_application_password" "this" {
  application_id = azuread_application_registration.this.id
  display_name          = "${var.app_secret_name}-${random_integer.number.result}"
  end_date     = "2026-07-02T00:00:00+00:00" # 1 year
}
