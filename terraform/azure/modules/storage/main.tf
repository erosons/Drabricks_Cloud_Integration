terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 3.0"
    }
  }
}

resource "azurerm_storage_account" "metastore" {
  name                      = replace("${var.environment}dbxmeta${var.project_name}", "-", "")
  resource_group_name       = var.resource_group_name
  location                  = var.location
  account_tier              = "Standard"
  account_replication_type  = var.storage_replication_type
  enable_https_traffic_only = true
  min_tls_version           = "TLS1_2"
  access_tier               = var.storage_access_tier

  network_rules {
    default_action             = "Deny"
    virtual_network_subnet_ids = var.allowed_subnet_ids
    bypass                     = ["AzureServices"]
  }

  identity {
    type = "SystemAssigned"
  }

  blob_properties {
    versioning_enabled       = var.enable_blob_versioning
    last_access_time_enabled = var.enable_last_access_time
    delete_retention_policy {
      days = var.blob_delete_retention_days
    }
    container_delete_retention_policy {
      days = var.container_delete_retention_days
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.environment}-metastore-storage"
    Type = "Metastore"
  })
}

# Separate ADLS Gen2 storage account for the data lake (optional)
resource "azurerm_storage_account" "data" {
  count                     = var.create_separate_data_storage ? 1 : 0
  name                      = replace("${var.environment}dbxdata${var.project_name}", "-", "")
  resource_group_name       = var.resource_group_name
  location                  = var.location
  account_tier              = "Standard"
  account_replication_type  = var.storage_replication_type
  enable_https_traffic_only = true
  min_tls_version           = "TLS1_2"
  access_tier               = var.storage_access_tier
  is_hns_enabled            = true

  network_rules {
    default_action             = "Deny"
    virtual_network_subnet_ids = var.allowed_subnet_ids
    bypass                     = ["AzureServices"]
  }

  identity {
    type = "SystemAssigned"
  }

  blob_properties {
    versioning_enabled       = var.enable_blob_versioning
    last_access_time_enabled = var.enable_last_access_time
    delete_retention_policy {
      days = var.blob_delete_retention_days
    }
  }

  tags = merge(var.common_tags, {
    Name = "${var.environment}-data-storage"
    Type = "DataLake"
  })
}

resource "azurerm_storage_container" "metastore" {
  name                  = var.metastore_container_name
  storage_account_name  = azurerm_storage_account.metastore.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "data" {
  name                  = var.data_container_name
  storage_account_name  = azurerm_storage_account.metastore.name
  container_access_type = "private"
}

resource "azurerm_storage_container" "data_lake" {
  count                 = var.create_separate_data_storage ? 1 : 0
  name                  = var.data_container_name
  storage_account_name  = azurerm_storage_account.data[0].name
  container_access_type = "private"
}

resource "azurerm_private_endpoint" "metastore_blob" {
  count               = var.enable_private_endpoints ? 1 : 0
  name                = "${var.environment}-metastore-blob-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_subnet_id

  private_service_connection {
    name                           = "metastore-blob-connection"
    private_connection_resource_id = azurerm_storage_account.metastore.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  tags = merge(var.common_tags, { Name = "${var.environment}-metastore-blob-pe" })
}

resource "azurerm_private_dns_a_record" "metastore_blob" {
  count               = var.enable_private_endpoints ? 1 : 0
  name                = azurerm_storage_account.metastore.name
  zone_name           = var.blob_private_dns_zone_name
  resource_group_name = var.resource_group_name
  ttl                 = 300
  records = [
    azurerm_private_endpoint.metastore_blob[0].private_service_connection[0].private_ip_address
  ]
}

resource "azurerm_private_endpoint" "data_blob" {
  count               = var.enable_private_endpoints && var.create_separate_data_storage ? 1 : 0
  name                = "${var.environment}-data-blob-pe"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_subnet_id

  private_service_connection {
    name                           = "data-blob-connection"
    private_connection_resource_id = azurerm_storage_account.data[0].id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  tags = merge(var.common_tags, { Name = "${var.environment}-data-blob-pe" })
}

resource "azurerm_private_dns_a_record" "data_blob" {
  count               = var.enable_private_endpoints && var.create_separate_data_storage ? 1 : 0
  name                = azurerm_storage_account.data[0].name
  zone_name           = var.blob_private_dns_zone_name
  resource_group_name = var.resource_group_name
  ttl                 = 300
  records = [
    azurerm_private_endpoint.data_blob[0].private_service_connection[0].private_ip_address
  ]
}

resource "azurerm_storage_account_customer_managed_key" "metastore" {
  count                     = var.enable_cmk ? 1 : 0
  storage_account_id        = azurerm_storage_account.metastore.id
  key_vault_id              = var.key_vault_id
  key_name                  = var.key_vault_key_name
  key_version               = var.key_vault_key_version
  user_assigned_identity_id = var.user_assigned_identity_id
}
