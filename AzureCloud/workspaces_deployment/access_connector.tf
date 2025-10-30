
resource "azurerm_databricks_access_connector" "this" {
  name                = "${var.dbx_access_connetor}-${random_integer.number.result}"
  resource_group_name = var.resource_group
  location            = var.region
  identity {
    type = "SystemAssigned"
  }

  tags = {
    Environment = "POC"
  }
  depends_on = [ azurerm_databricks_workspace.this,azurerm_storage_account.this ,azurerm_resource_group.rg]
}