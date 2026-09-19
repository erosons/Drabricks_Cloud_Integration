terraform {
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
    }
    databricks = {
      source  = "databricks/databricks"
    }
  }
}

#######################################
#Authentication layer Azure CLI on local
######################################
# The azurerm provider is configured to use Azure CLI credentials (az login) for authentication.
#  If additional credentials like client_id, client_secret, or tenant_id are needed, they can be added.

provider "azurerm" {
  features {}
   subscription_id ="948bd2bd-6f43-41f7-872c-d3a8c2b0656a"
#   client_id = 
#   client_secret = 
#   tenant_id = 

}

# The data "azurerm_client_config" "current" block retrieves information about the authenticated Azure account, such as tenant_id and object_id.
data "azurerm_client_config" "current" {}


# Retrieve the details of an existing Databricks workspace using the azurerm_databricks_workspace data source.
data "azurerm_databricks_workspace" "example" {
  name                = "databricks-warehous3"
  resource_group_name = "databricks"
}



#######################################
#Authentication into Databricks
######################################
# The databricks provider uses the workspace URL and Azure resource ID to authenticate and interact with the Databricks environment.
provider "databricks" {
  host                        = data.azurerm_databricks_workspace.example.workspace_url
  azure_workspace_resource_id = data.azurerm_databricks_workspace.example.id
}


data "azurerm_resource_group" "rg" {
  name = "databricks"
}


# Storage Account
resource "azurerm_storage_account" "databricks_storage" {
  name                     = "databricksstorageacct5"
  resource_group_name      = data.azurerm_resource_group.rg.name
  location                 = data.azurerm_resource_group.rg.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  blob_properties {
    delete_retention_policy {
      days    = 7
    }
  }

  tags = {
    environment = "dev"
    project     = "databricks"
  }
}

resource "azurerm_storage_container" "container" {
  name =   "azuredbcomtainer"
  storage_account_id= azurerm_storage_account.databricks_storage.id
}


# Creates an Azure Key Vault to securely manage secrets like the storage account keys.
resource "azurerm_key_vault" "keyvault" {
  name                        = "azuredbkeylv2027"
  resource_group_name      = data.azurerm_resource_group.rg.name
  location                 = data.azurerm_resource_group.rg.location
  enabled_for_disk_encryption = true
  tenant_id                   = data.azurerm_client_config.current.tenant_id
  soft_delete_retention_days  = 7
  purge_protection_enabled    = false

  sku_name = "standard"

#   access_policy {
#     tenant_id = data.azurerm_client_config.current.tenant_id
#     object_id = data.azurerm_client_config.current.object_id

#     key_permissions = [
#       "Get",
#     ]

#     secret_permissions = [
#       "Get",
#     ]

#     storage_permissions = [
#       "Get",
#     ]
#   }
}

# Access policies are set for the authenticated user to allow actions like getting and setting secrets.
resource "azurerm_key_vault_access_policy" "kv" {
    object_id = data.azurerm_client_config.current.object_id
    tenant_id = data.azurerm_client_config.current.tenant_id
    key_vault_id = azurerm_key_vault.keyvault.id
    secret_permissions = ["Get","List","Set","Delete"]
  
}
# Creating the databrick and backend -> in this scenaro we are using AKV backend scenario
# Integrates Azure Key Vault with Databricks by creating a secret scope.
resource "databricks_secret_scope" "db_secret_scp" {
  name = "data_analyst_scope"
  keyvault_metadata {
    resource_id =azurerm_key_vault.keyvault.id
    dns_name = azurerm_key_vault.keyvault.vault_uri
    
  }  
}

resource "azurerm_key_vault_secret" "secret" {
    name = "azuredb-test"
    value = azurerm_storage_account.databricks_storage.primary_access_key
    key_vault_id = azurerm_key_vault.keyvault.id
}

output "id" {
  value = data.azurerm_resource_group.rg.id
}