
resource_group          = "samson-databricks-rg"
region                  = "East US"
workspace_name          = "samson-databricks-wk-sbx"
subscription_id         = ""
dbx_access_connetor     = "samson-access-connector-sbx"
secret_scope_name       = "samson-databricks-secret-scope"
storage_account_name    = "samstorage"
keyvault_name           = "sam-keyvault"
container_name          = "samson-databricks-container"
app_name               = "samson-databricks-app"
app_secret_name        = "samson-databricks-app-secret"
sku_value               = "premium"
//aad_groups              = ["account_unity_admin", "data_engineer", "data_analyst", "data_scientist"]
tags = {
  "Project" = "POC"
  "Environment" = "Sandbox"
  "Owner" = "Samson"
}




