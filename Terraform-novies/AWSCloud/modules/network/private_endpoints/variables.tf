# Back-end Workspace (REST/API) – workspace VPC.
# Back-end SCC Relay – workspace VPC (port 6666).
# Front-end (UI/API) – transit VPC.
# Enable “DNS name” on endpoints; for third-party services this gives the VPCE DNS names you’ll CNAME/A-record to. 
# Databricks Documentation

variable "name_prefix"          { type = string }
variable "workspace_vpc_id"     { type = string }
variable "backend_subnet_id"    { type = string }
variable "backend_sg_id"        { type = string }
variable "transit_vpc_id"       { type = string }
variable "frontend_subnet_id"   { type = string }
variable "frontend_sg_id"       { type = string }
variable "svc_name_workspace"   { type = string } # Databricks "Workspace" service name (region-specific)
variable "svc_name_scc_relay"   { type = string } # Databricks "SCC relay" service name (region-specific)
variable "tags"                 { type = map(string) default = {} }
