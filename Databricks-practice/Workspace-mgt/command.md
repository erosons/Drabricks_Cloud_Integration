# Know details about your Workspaces 
az databricks workspace show --resource-group databricks --name databrick-warehouse

## Assigning Permission to Workspace SPN Idenity (APPID) -> user assign a Permission to retrieval sevret from key vault.
az role assignment create \
  --assignee 2ff814a6-3304-4ab8-85cb-cd0e6f879c1d \
  --role "Key Vault Administrator" \
  --scope "/subscriptions/948bd2bd-6f43-41f7-872c-d3a8c2b0656a/resourceGroups/databricks/providers/Microsoft.KeyVault/vaults/databrickvault001"

## List Scopes and screts within scope
 databricks secrets list-scopes 
 databricks secrets list --scope data_analyst_scope