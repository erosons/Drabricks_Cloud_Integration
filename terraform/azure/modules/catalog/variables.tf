variable "environment"   { type = string }
variable "domain"        { type = string }
variable "catalog_name"  { type = string }
variable "schemas"       { type = list(string) }

output "catalog_name" { value = databricks_catalog.domain.name }
output "catalog_id"   { value = databricks_catalog.domain.id }
output "schema_names" { value = { for k, v in databricks_schema.default_schemas : k => v.name } }
