# Retrieve information about the current Azure subscription
data "azurerm_subscription" "primary" {}

# Use an existing resource group if it already exists
data "azurerm_resource_group" "existing_rg" {
  name = var.resource_group_name
  count = length(data.azurerm_subscription.primary.id) > 0 ? 1 : 0
}
