variable "environment"               { type = string }
variable "catalog_name"              { type = string }
variable "domain_tables"             { type = map(list(any)) }
variable "domains_in_catalog"        { type = list(string) }
variable "dlt_pipeline_exempt_group" { type = string }
variable "time_travel_exempt_group"  { type = string }

output "region_filter_function_names" {
  value = { for k, v in databricks_sql_function.row_filter_region_scoped : k => v.name }
}
output "entity_filter_function_names" {
  value = { for k, v in databricks_sql_function.row_filter_entity_scoped : k => v.name }
}
output "classification_filter_function_names" {
  value = { for k, v in databricks_sql_function.row_filter_classification : k => v.name }
}
