output "discovered_metastore_id" { value = local.discovered_metastore_id }
output "create_uc_metastore"     { value = local.create_uc_metastore }
output "effective_metastore_id"  { value = local.metastore_id }

output "workspace_id"       { value = databricks_mws_workspaces.ws.workspace_id }
output "workspace_hostname" { value = databricks_mws_workspaces.ws.workspace_url } # <deployment>.cloud.databricks.com
