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

#####################
#Authentication layer
#####################

provider "azurerm" {
  features {}
  subscription_id ="948bd2bd-6f43-41f7-872c-d3a8c2b0656a"
  client_id = 
  client_secret = 
  tenant_id = 

}

provider "databricks" {
  # host = azurerm_databricks_workspace.this.workspace_url
  azure_workspace_resource_id =azurerm_databricks_workspace.workspace.id
}



locals {
  tenant_id    = "00000000-1111-2222-3333-444444444444"
  client_id    = "55555555-6666-7777-8888-999999999999"
  secret_scope = "some-kv"
  secret_key   = "some-sp-secret"
  container    = "test"
  storage_acc  = "lrs"
}

resource "databricks_mount" "this" {
  name = "tf-abfss"

  uri = "abfss://${local.container}@${local.storage_acc}.dfs.core.windows.net"
  extra_configs = {
    "fs.azure.account.auth.type" : "OAuth",
    "fs.azure.account.oauth.provider.type" : "org.apache.hadoop.fs.azurebfs.oauth2.ClientCredsTokenProvider",
    "fs.azure.account.oauth2.client.id" : local.client_id,
    "fs.azure.account.oauth2.client.secret" : "{{secrets/${local.secret_scope}/${local.secret_key}}}",
    "fs.azure.account.oauth2.client.endpoint" : "https://login.microsoftonline.com/${local.tenant_id}/oauth2/token",
    "fs.azure.createRemoteFileSystemDuringInitialization" : "false",
  }
}