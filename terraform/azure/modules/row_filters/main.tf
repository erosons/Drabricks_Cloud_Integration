# ─────────────────────────────────────────────
# Module: row_filters
# Deploys row filter functions for each table
# using the correct archetype template.
# Functions are created in a dedicated
# _policies schema inside each catalog.
# ─────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.38.0"
    }
  }
}

# ── Dedicated schema for policy functions ─────

resource "databricks_schema" "policies" {
  provider     = databricks.workspace
  catalog_name = var.catalog_name
  name         = "_policies"
  comment      = "Row filter and column mask functions — do not modify manually"
}

# ── Row filter: region scoped ─────────────────
# Groups checked: dlt_pipeline_exempt, time_travel_exempt,
#   {env}_{domain}_{table}_region_{apac|emea|amer|global}

resource "databricks_sql_function" "row_filter_region_scoped" {
  provider     = databricks.workspace
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : {
          key       = "${domain}_${tbl.table_name}"
          domain    = domain
          table     = tbl.table_name
          filter_col = tbl.row_filter_col
        } if tbl.row_filter_type == "region_scoped"
      ]
    ]) : pair.key => pair
  }

  name         = "row_filter_${each.value.table}_region"
  catalog_name = var.catalog_name
  schema_name  = "_policies"
  input_params {
    name      = "filter_col_value"
    type_text = "STRING"
  }
  return_type { type_text = "BOOLEAN" }
  routine_body = "SQL"
  body = <<-SQL
    CASE
      -- Exempt: DLT pipelines read full dataset for materialisation
      WHEN is_account_group_member('${var.dlt_pipeline_exempt_group}')   THEN TRUE
      -- Exempt: time travel / audit users bypass filter
      WHEN is_account_group_member('${var.time_travel_exempt_group}')    THEN TRUE
      -- Exempt: domain admin
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_admin') THEN TRUE
      -- Functional: region-scoped access
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_region_global') THEN TRUE
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_region_apac')   THEN filter_col_value = 'APAC'
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_region_emea')   THEN filter_col_value = 'EMEA'
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_region_amer')   THEN filter_col_value = 'AMER'
      -- Default: deny
      ELSE FALSE
    END
  SQL
  comment = "Row filter for ${each.value.table} — region dimension. Managed by Terraform."
}

# ── Row filter: entity scoped ─────────────────

resource "databricks_sql_function" "row_filter_entity_scoped" {
  provider = databricks.workspace
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : {
          key        = "${domain}_${tbl.table_name}"
          domain     = domain
          table      = tbl.table_name
          filter_col = tbl.row_filter_col
        } if tbl.row_filter_type == "entity_scoped"
      ]
    ]) : pair.key => pair
  }

  name         = "row_filter_${each.value.table}_entity"
  catalog_name = var.catalog_name
  schema_name  = "_policies"
  input_params {
    name      = "filter_col_value"
    type_text = "STRING"
  }
  return_type { type_text = "BOOLEAN" }
  routine_body = "SQL"
  body = <<-SQL
    CASE
      WHEN is_account_group_member('${var.dlt_pipeline_exempt_group}')   THEN TRUE
      WHEN is_account_group_member('${var.time_travel_exempt_group}')    THEN TRUE
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_admin') THEN TRUE
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_all_entities')   THEN TRUE
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_bu_retail')      THEN filter_col_value = 'RETAIL'
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_bu_wholesale')   THEN filter_col_value = 'WHOLESALE'
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_bu_corporate')   THEN filter_col_value = 'CORPORATE'
      ELSE FALSE
    END
  SQL
  comment = "Row filter for ${each.value.table} — entity dimension. Managed by Terraform."
}

# ── Row filter: classification scoped ────────

resource "databricks_sql_function" "row_filter_classification" {
  provider = databricks.workspace
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : {
          key    = "${domain}_${tbl.table_name}"
          domain = domain
          table  = tbl.table_name
        } if tbl.row_filter_type == "classification"
      ]
    ]) : pair.key => pair
  }

  name         = "row_filter_${each.value.table}_classification"
  catalog_name = var.catalog_name
  schema_name  = "_policies"
  input_params {
    name      = "filter_col_value"
    type_text = "STRING"
  }
  return_type { type_text = "BOOLEAN" }
  routine_body = "SQL"
  body = <<-SQL
    CASE
      WHEN is_account_group_member('${var.dlt_pipeline_exempt_group}')   THEN TRUE
      WHEN is_account_group_member('${var.time_travel_exempt_group}')    THEN TRUE
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_admin') THEN TRUE
      -- Restricted can see all classifications
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_class_restricted')  THEN TRUE
      -- Confidential can see confidential and below
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_class_confidential') THEN filter_col_value IN ('PUBLIC','INTERNAL','CONFIDENTIAL')
      -- Internal can see internal and below
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_class_internal')    THEN filter_col_value IN ('PUBLIC','INTERNAL')
      -- Public only
      WHEN is_account_group_member('${var.environment}_${each.value.domain}_${each.value.table}_class_public')      THEN filter_col_value = 'PUBLIC'
      ELSE FALSE
    END
  SQL
  comment = "Row filter for ${each.value.table} — classification dimension. Managed by Terraform."
}

# ── EXECUTE grants on filter functions ────────
# Structural reader group must be able to execute
# the filter function when they query the table

resource "databricks_grants" "row_filter_execute" {
  provider = databricks.workspace
  for_each = merge(
    { for k, v in databricks_sql_function.row_filter_region_scoped : k => v.name },
    { for k, v in databricks_sql_function.row_filter_entity_scoped : k => v.name },
    { for k, v in databricks_sql_function.row_filter_classification : k => v.name }
  )

  function = "${var.catalog_name}._policies.${each.value}"

  dynamic "grant" {
    for_each = toset(var.domains_in_catalog)
    content {
      principal  = "${var.environment}_${grant.value}_reader"
      privileges = ["EXECUTE"]
    }
  }
}
