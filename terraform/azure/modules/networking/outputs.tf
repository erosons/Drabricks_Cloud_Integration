output "vnet_id" {
  description = "ID of the Virtual Network"
  value       = azurerm_virtual_network.main.id
}

output "vnet_name" {
  description = "Name of the Virtual Network"
  value       = azurerm_virtual_network.main.name
}

output "public_subnet_id" {
  description = "ID of the public subnet"
  value       = azurerm_subnet.public.id
}

output "public_subnet_name" {
  description = "Name of the public subnet"
  value       = azurerm_subnet.public.name
}

output "private_subnet_id" {
  description = "ID of the private subnet"
  value       = azurerm_subnet.private.id
}

output "private_subnet_name" {
  description = "Name of the private subnet"
  value       = azurerm_subnet.private.name
}

output "nsg_id" {
  description = "ID of the Network Security Group"
  value       = azurerm_network_security_group.main.id
}

output "nsg_name" {
  description = "Name of the Network Security Group"
  value       = azurerm_network_security_group.main.name
}

# azurerm_databricks_workspace custom_parameters requires the NSG *association* resource ID,
# not the NSG ID itself.
output "public_nsg_association_id" {
  description = "ID of the public subnet NSG association resource"
  value       = azurerm_subnet_network_security_group_association.public.id
}

output "private_nsg_association_id" {
  description = "ID of the private subnet NSG association resource"
  value       = azurerm_subnet_network_security_group_association.private.id
}

output "blob_private_dns_zone_name" {
  description = "Name of the private DNS zone for blob storage (used as zone_name in DNS A records)"
  value       = try(azurerm_private_dns_zone.blob_storage[0].name, null)
}

output "blob_private_dns_zone_id" {
  description = "ARM resource ID of the private DNS zone for blob storage"
  value       = try(azurerm_private_dns_zone.blob_storage[0].id, null)
}

output "sql_private_dns_zone_id" {
  description = "ARM resource ID of the private DNS zone for SQL"
  value       = try(azurerm_private_dns_zone.sql_database[0].id, null)
}

output "network_config" {
  description = "Complete network configuration summary"
  value = {
    vnet_id                    = azurerm_virtual_network.main.id
    public_subnet_id           = azurerm_subnet.public.id
    private_subnet_id          = azurerm_subnet.private.id
    nsg_id                     = azurerm_network_security_group.main.id
    public_nsg_association_id  = azurerm_subnet_network_security_group_association.public.id
    private_nsg_association_id = azurerm_subnet_network_security_group_association.private.id
    blob_dns_zone_name         = try(azurerm_private_dns_zone.blob_storage[0].name, null)
    sql_dns_zone_id            = try(azurerm_private_dns_zone.sql_database[0].id, null)
  }
}
