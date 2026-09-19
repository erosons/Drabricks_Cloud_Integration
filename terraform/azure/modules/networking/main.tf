terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

resource "azurerm_virtual_network" "main" {
  name                = "${var.environment}-${var.project_name}-vnet"
  address_space       = var.vnet_address_space
  location            = var.location
  resource_group_name = var.resource_group_name

  tags = merge(var.common_tags, { Name = "${var.environment}-vnet" })
}

resource "azurerm_subnet" "public" {
  name                 = "${var.environment}-public-subnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.public_subnet_prefix]

  service_endpoints = ["Microsoft.Storage", "Microsoft.KeyVault", "Microsoft.Sql"]

  delegation {
    name = "databricks"
    service_delegation {
      name = "Microsoft.Databricks/workspaces"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
        "Microsoft.Network/virtualNetworks/subnets/prepareNetworkPolicies/action",
        "Microsoft.Network/virtualNetworks/subnets/unprepareNetworkPolicies/action",
      ]
    }
  }
}

# Both subnets require the Databricks delegation for VNet injection
resource "azurerm_subnet" "private" {
  name                 = "${var.environment}-private-subnet"
  resource_group_name  = var.resource_group_name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = [var.private_subnet_prefix]

  service_endpoints = ["Microsoft.Storage", "Microsoft.KeyVault", "Microsoft.Sql"]

  delegation {
    name = "databricks"
    service_delegation {
      name = "Microsoft.Databricks/workspaces"
      actions = [
        "Microsoft.Network/virtualNetworks/subnets/join/action",
        "Microsoft.Network/virtualNetworks/subnets/prepareNetworkPolicies/action",
        "Microsoft.Network/virtualNetworks/subnets/unprepareNetworkPolicies/action",
      ]
    }
  }
}

resource "azurerm_network_security_group" "main" {
  name                = "${var.environment}-${var.project_name}-nsg"
  location            = var.location
  resource_group_name = var.resource_group_name

  tags = merge(var.common_tags, { Name = "${var.environment}-nsg" })
}

resource "azurerm_network_security_rule" "allow_vnet_inbound" {
  name                        = "AllowVNetInbound"
  priority                    = 100
  direction                   = "Inbound"
  access                      = "Allow"
  protocol                    = "*"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "VirtualNetwork"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.main.name
}

resource "azurerm_network_security_rule" "allow_azure_services_outbound" {
  name                        = "AllowAzureServicesOutbound"
  priority                    = 100
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "*"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "AzureCloud"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.main.name
}

resource "azurerm_network_security_rule" "allow_internet_https_outbound" {
  name                        = "AllowInternetHttpsOutbound"
  priority                    = 101
  direction                   = "Outbound"
  access                      = "Allow"
  protocol                    = "Tcp"
  source_port_range           = "*"
  destination_port_range      = "443"
  source_address_prefix       = "VirtualNetwork"
  destination_address_prefix  = "Internet"
  resource_group_name         = var.resource_group_name
  network_security_group_name = azurerm_network_security_group.main.name
}

resource "azurerm_subnet_network_security_group_association" "public" {
  subnet_id                 = azurerm_subnet.public.id
  network_security_group_id = azurerm_network_security_group.main.id
}

resource "azurerm_subnet_network_security_group_association" "private" {
  subnet_id                 = azurerm_subnet.private.id
  network_security_group_id = azurerm_network_security_group.main.id
}

resource "azurerm_private_dns_zone" "blob_storage" {
  count               = var.enable_private_endpoints ? 1 : 0
  name                = "privatelink.blob.core.windows.net"
  resource_group_name = var.resource_group_name

  tags = merge(var.common_tags, { Name = "privatelink-blob-dns" })
}

resource "azurerm_private_dns_zone_virtual_network_link" "blob_storage" {
  count                 = var.enable_private_endpoints ? 1 : 0
  name                  = "${var.environment}-blob-dns-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.blob_storage[0].name
  virtual_network_id    = azurerm_virtual_network.main.id

  tags = merge(var.common_tags, { Name = "${var.environment}-blob-dns-link" })
}

resource "azurerm_private_dns_zone" "sql_database" {
  count               = var.enable_private_endpoints ? 1 : 0
  name                = "privatelink.database.windows.net"
  resource_group_name = var.resource_group_name

  tags = merge(var.common_tags, { Name = "privatelink-sql-dns" })
}

resource "azurerm_private_dns_zone_virtual_network_link" "sql_database" {
  count                 = var.enable_private_endpoints ? 1 : 0
  name                  = "${var.environment}-sql-dns-link"
  resource_group_name   = var.resource_group_name
  private_dns_zone_name = azurerm_private_dns_zone.sql_database[0].name
  virtual_network_id    = azurerm_virtual_network.main.id

  tags = merge(var.common_tags, { Name = "${var.environment}-sql-dns-link" })
}
