output "structural_group_ids" {
  value = { for k, v in databricks_group.structural : k => v.id }
}

output "exempt_group_ids" {
  value = { for k, v in databricks_group.exempt : k => v.id }
}

output "region_group_ids" {
  value = { for k, v in databricks_group.region_scoped : k => v.id }
}

output "entity_group_ids" {
  value = { for k, v in databricks_group.entity_scoped : k => v.id }
}

output "classification_group_ids" {
  value = { for k, v in databricks_group.classification_scoped : k => v.id }
}

output "pii_group_ids" {
  value = { for k, v in databricks_group.pii_access : k => v.id }
}

output "financial_group_ids" {
  value = { for k, v in databricks_group.financial_access : k => v.id }
}
