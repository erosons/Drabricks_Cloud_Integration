resource "azurerm_virtual_network" "ws" {
  name                = var.vnet_name
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.vnet_cidr]
  tags                = var.tags
}

resource "azurerm_subnet" "public" {
  name                 = "adb-public"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.ws.name
  address_prefixes     = [var.public_subnet_cidr]
}

resource "azurerm_subnet" "private" {
  name                 = "adb-private"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.ws.name
  address_prefixes     = [var.private_subnet_cidr]
}

# PE subnet: enable Private Endpoint policies, avoid NSG
resource "azurerm_subnet" "pe" {
  name                 = "adb-pe"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.ws.name
  address_prefixes     = [var.pe_subnet_cidr]
  enforce_private_link_endpoint_network_policies = true
}

# Optional transit VNet for front-end PEs
resource "azurerm_virtual_network" "transit" {
  count               = var.create_transit_vnet ? 1 : 0
  name                = var.transit_vnet_name
  location            = var.location
  resource_group_name = var.resource_group_name
  address_space       = [var.transit_vnet_cidr]
  tags                = var.tags
}

resource "azurerm_subnet" "transit_pe" {
  count                = var.create_transit_vnet ? 1 : 0
  name                 = var.transit_pe_subnet_name
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.transit[0].name
  address_prefixes     = [var.transit_pe_subnet_cidr]
  enforce_private_link_endpoint_network_policies = true
}
