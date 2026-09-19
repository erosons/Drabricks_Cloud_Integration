# Notes

#     Permissions: Ensure the Managed Identity used 
#     for authentication has the Contributor role on the Databricks workspace or at the subscription level.
#     Azure Environment: This setup assumes you’re working within an
#     Azure environment where MSI is available, such as an Azure Virtual Machine, Azure App Service, or Azure Kubernetes Service (AKS) with the correct permissions.

provider "databricks" {
  host                        = data.azurerm_databricks_workspace.this.workspace_url
  azure_workspace_resource_id = azurerm_databricks_workspace.databricks.id
  azure_use_msi               = true
}
