# Back-end PE (SCC relay path) - group id: databricks_ui_api
resource "azurerm_private_endpoint" "backend" {
  name                = "${var.name_prefix}-backend-pe"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.backend_subnet_id

  private_service_connection {
    name                           = "dbx-backend"
    private_connection_resource_id = var.ws_id
    subresource_names              = ["databricks_ui_api"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dbx-backend-dns"
    private_dns_zone_ids = [var.dns_zone_id]
  }

  tags = var.tags
}

# Front-end PE (UI/API) - group id: databricks_ui_api
resource "azurerm_private_endpoint" "frontend_uiapi" {
  name                = "${var.name_prefix}-frontend-uiapi-pe"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.frontend_subnet_id

  private_service_connection {
    name                           = "dbx-frontend-uiapi"
    private_connection_resource_id = var.ws_id
    subresource_names              = ["databricks_ui_api"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dbx-frontend-uiapi-dns"
    private_dns_zone_ids = [var.dns_zone_id]
  }

  tags = var.tags
}

# Front-end PE (browser authentication) - group id: browser_authentication
resource "azurerm_private_endpoint" "browser_auth" {
  name                = "${var.name_prefix}-browser-auth-pe"
  resource_group_name = var.resource_group_name
  location            = var.location
  subnet_id           = var.frontend_subnet_id

  private_service_connection {
    name                           = "dbx-browser-auth"
    private_connection_resource_id = var.ws_id
    subresource_names              = ["browser_authentication"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "dbx-browser-auth-dns"
    private_dns_zone_ids = [var.dns_zone_id]
  }

  tags = var.tags
}
