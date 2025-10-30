
resource "azurerm_storage_container" "this" {
  name                  = "${var.container_name}-${random_integer.number.result}"
  storage_account_id    = azurerm_storage_account.this.id

  depends_on            = [azurerm_storage_account.this]
}
