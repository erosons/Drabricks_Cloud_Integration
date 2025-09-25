variable "zone_id"            { type = string }
variable "workspace_hostname" { type = string } # "<deployment>.cloud.databricks.com"
variable "workspace_id"       { type = string } # "dbc-dp-xxxxxxxxxxxx"
variable "frontend_vpce_ip"   { type = string } # from module.private_endpoints.frontend_vpce_ip
