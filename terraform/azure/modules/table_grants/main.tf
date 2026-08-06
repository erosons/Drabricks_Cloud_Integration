# ─────────────────────────────────────────────
# Module: table_grants
# For each table in a domain:
#   1. Grant SELECT to structural reader/writer groups
#   2. Attach row filter function to table
#   3. Attach column mask functions to PII/financial cols
#
# IMPORTANT: This module assumes the table already
# exists (created by your ETL/DLT pipeline).
# Use data sources to reference existing tables.
# ─────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.38.0"
    }
  }
}

# ── SELECT grants per table ───────────────────

resource "databricks_grants" "table_select" {
  provider = databricks.workspace
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : {
          key     = "${domain}_${tbl.schema_name}_${tbl.table_name}"
          domain  = domain
          schema  = tbl.schema_name
          table   = tbl.table_name
        }
      ]
    ]) : pair.key => pair
  }

  table = "${var.catalog_name}.${each.value.schema}.${each.value.table}"

  grant {
    principal  = "${var.environment}_${each.value.domain}_reader"
    privileges = ["SELECT"]
  }
  grant {
    principal  = "${var.environment}_${each.value.domain}_writer"
    privileges = ["SELECT", "MODIFY"]
  }
  grant {
    principal  = "${var.environment}_${each.value.domain}_admin"
    privileges = ["SELECT", "MODIFY", "ALL_PRIVILEGES"]
  }
}

# ── Row filter attachment ─────────────────────
# Uses databricks_table to attach the row filter.
# The filter function name is derived from the archetype.

resource "databricks_table" "row_filter_attachment" {
  provider = databricks.workspace
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : {
          key             = "${domain}_${tbl.schema_name}_${tbl.table_name}"
          domain          = domain
          schema          = tbl.schema_name
          table           = tbl.table_name
          filter_type     = tbl.row_filter_type
          filter_col      = tbl.row_filter_col
        } if tbl.row_filter_type != "none"
      ]
    ]) : pair.key => pair
  }

  catalog_name = var.catalog_name
  schema_name  = each.value.schema
  name         = each.value.table

  # Row filter function reference — pattern matches function naming in row_filters module
  row_filter {
    function_name = "${var.catalog_name}._policies.row_filter_${each.value.table}_${each.value.filter_type == "region_scoped" ? "region" : each.value.filter_type == "entity_scoped" ? "entity" : "classification"}"
    input_column_names = [each.value.filter_col]
  }
}

# ── Column mask attachment — PII columns ──────

resource "databricks_table" "pii_mask_attachment" {
  provider = databricks.workspace
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : {
          key         = "${domain}_${tbl.schema_name}_${tbl.table_name}"
          domain      = domain
          schema      = tbl.schema_name
          table       = tbl.table_name
          pii_columns = tbl.pii_columns
        } if length(tbl.pii_columns) > 0
      ]
    ]) : pair.key => pair
  }

  catalog_name = var.catalog_name
  schema_name  = each.value.schema
  name         = each.value.table

  dynamic "column" {
    for_each = toset(each.value.pii_columns)
    content {
      name = column.value
      mask {
        function_name      = "${var.catalog_name}._policies.col_mask_pii_${each.value.domain}"
        using_column_names = [column.value]
      }
    }
  }
}

# ── Column mask attachment — financial columns ─

resource "databricks_table" "financial_mask_attachment" {
  provider = databricks.workspace
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : {
          key               = "${domain}_${tbl.schema_name}_${tbl.table_name}"
          domain            = domain
          schema            = tbl.schema_name
          table             = tbl.table_name
          financial_columns = tbl.financial_columns
        } if length(tbl.financial_columns) > 0
      ]
    ]) : pair.key => pair
  }

  catalog_name = var.catalog_name
  schema_name  = each.value.schema
  name         = each.value.table

  dynamic "column" {
    for_each = toset(each.value.financial_columns)
    content {
      name = column.value
      mask {
        function_name      = "${var.catalog_name}._policies.col_mask_financial_${each.value.domain}"
        using_column_names = [column.value]
      }
    }
  }
}
