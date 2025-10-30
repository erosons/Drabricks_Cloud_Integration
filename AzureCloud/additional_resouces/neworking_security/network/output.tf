output "vnet_id" {
  value = azurerm_virtual_network.ws.id
}

output "public_subnet_name" {
  value = azurerm_subnet.public.name
}

output "private_subnet_name" {
  value = azurerm_subnet.private.name
}

output "pe_subnet_id" {
  value = azurerm_subnet.pe.id
}

output "transit_vnet_id" {
  value = try(azurerm_virtual_network.transit[0].id, null)
}

output "transit_pe_subnet_id" {
  value = try(azurerm_subnet.transit_pe[0].id, null)
}

