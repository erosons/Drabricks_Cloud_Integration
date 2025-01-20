resource_group_name        = "my-dev-rg"
location                   = "East US"
databricks_workspace_name  = "dev-databricks-workspace"
storage_account_name       = "devstorageacct"
container_name             = "dev-container"






# To run the script
terraform apply -var-file="dev.tfvars"