variable "ws_id"             { type = string }   # azurerm_databricks_workspace.this.id
variable "backend_subnet_id" { type = string }   # PE subnet in workspace VNet
variable "frontend_subnet_id"{ type = string }   # PE subnet in transit VNet
variable "dns_zone_id"       { type = string }   # privatelink.azuredatabricks.net zone id

variable "name_prefix" {
  type    = string
  default = "dbx"
}

variable "resource_group_name" { type = string }
variable "location"            { type = string }
variable "tags"                { type = map(string) default = {} }
