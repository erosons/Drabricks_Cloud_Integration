variable "environment"               { type = string }
variable "catalog_name"              { type = string }
variable "domains_in_catalog"        { type = list(string) }
variable "dlt_pipeline_exempt_group" { type = string }
variable "time_travel_exempt_group"  { type = string }

output "pii_mask_function_names" {
  value = { for k, v in databricks_sql_function.col_mask_pii : k => v.name }
}
output "financial_mask_function_names" {
  value = { for k, v in databricks_sql_function.col_mask_financial : k => v.name }
}
