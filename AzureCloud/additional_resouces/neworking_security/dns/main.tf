resource "azurerm_private_dns_zone" "this" {
  name                = var.dns_zone_name
  resource_group_name = var.dns_resource_group
  tags                = var.tags
}

resource "azurerm_private_dns_zone_virtual_network_link" "links" {
  for_each              = toset(var.vnet_ids)
  name                  = "link-${substr(replace(each.value, "/","-"), length(each.value)-12, 12)}"
  resource_group_name   = var.dns_resource_group
  private_dns_zone_name = azurerm_private_dns_zone.this.name
  virtual_network_id    = each.value
  registration_enabled  = false
}
