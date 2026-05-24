# Workspace VPC + private subnet (clusters) + PE subnet.
# Transit VPC + PE subnet (front-end).
# Minimal security groups: workspace SG, backend (SCC/workspace) SG, front-end SG with Databricks-documented ports

variable "name_prefix"            { type = string }
variable "vpc_cidr"               { type = string }
variable "ws_private_subnet_cidr" { type = string }
variable "ws_pe_subnet_cidr"      { type = string }
variable "transit_vpc_cidr"       { type = string }
variable "transit_pe_subnet_cidr" { type = string }
variable "tags"                   { type = map(string) default = {} }
