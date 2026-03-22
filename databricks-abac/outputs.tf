# ─────────────────────────────────────────────
# Outputs — useful for downstream references
# and for validating what was deployed
# ─────────────────────────────────────────────

output "catalog_names" {
  description = "All catalogs created in this environment"
  value       = { for k, v in module.catalog : k => v.catalog_name }
}

output "structural_group_ids" {
  description = "Account group IDs for structural groups"
  value       = module.access_groups.structural_group_ids
}

output "exempt_group_ids" {
  description = "Account group IDs for exempt groups"
  value       = module.access_groups.exempt_group_ids
}

output "row_filter_function_names" {
  description = "All deployed row filter function names, keyed by domain_table"
  value = merge(
    { for k, v in module.row_filters : k => v.region_filter_function_names },
    { for k, v in module.row_filters : k => v.entity_filter_function_names },
    { for k, v in module.row_filters : k => v.classification_filter_function_names }
  )
}

output "column_mask_function_names" {
  description = "All deployed column mask function names"
  value = merge(
    { for k, v in module.column_masks : k => v.pii_mask_function_names },
    { for k, v in module.column_masks : k => v.financial_mask_function_names }
  )
}

output "deployment_summary" {
  description = "Human-readable deployment summary"
  value = <<-EOT
    Environment : ${var.environment}
    Domains     : ${join(", ", var.domains)}
    Catalogs    : ${join(", ", [for k, v in module.catalog : v.catalog_name])}
    
    Run the validation notebook to verify policies:
    notebooks/validate_abac_policies.sql
  EOT
}
