
# Storage Account
resource "azurerm_storage_account" "this" {
  name                     = "${var.storage_account_name}${random_integer.number.result}"
  resource_group_name      = var.resource_group
  location                 = var.region
  account_tier             = "Standard"
  account_replication_type = "LRS"
  account_kind             = "StorageV2"
  is_hns_enabled           = "true"

  blob_properties {
    delete_retention_policy {
      days    = 7
    }
  }

  tags = {
    environment = "dev"
    project     = "databricks"
  }
  depends_on = [azurerm_resource_group.rg]
}