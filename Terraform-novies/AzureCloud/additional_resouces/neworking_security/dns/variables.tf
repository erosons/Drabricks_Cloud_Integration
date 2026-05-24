variable "dns_zone_name"      { type = string }         # e.g. privatelink.azuredatabricks.net
variable "dns_resource_group" { type = string }
variable "vnet_ids"           { type = list(string) }   # link zone to these VNets
variable "tags"               { type = map(string) default = {} }
