variable "resource_group_name" { type = string }
variable "location"            { type = string }

# Workspace VNet + subnets
variable "vnet_name"           { type = string }
variable "vnet_cidr"           { type = string } # e.g. 10.10.0.0/16
variable "public_subnet_cidr"  { type = string } # e.g. 10.10.1.0/24
variable "private_subnet_cidr" { type = string } # e.g. 10.10.2.0/24
variable "pe_subnet_cidr"      { type = string } # e.g. 10.10.3.0/27

# (Optional) create a small transit vnet to host front-end PEs
variable "create_transit_vnet" {
  type    = bool
  default = true
}
variable "transit_vnet_name" {
  type    = string
  default = "vnet-dbx-transit"
}
variable "transit_vnet_cidr" {
  type    = string
  default = "10.20.0.0/16"
}
variable "transit_pe_subnet_name" {
  type    = string
  default = "pl-endpoints"
}
variable "transit_pe_subnet_cidr" {
  type    = string
  default = "10.20.1.0/27"
}

variable "tags" { type = map(string) default = {} }
