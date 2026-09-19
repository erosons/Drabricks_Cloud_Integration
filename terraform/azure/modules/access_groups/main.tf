# ─────────────────────────────────────────────
# Module: access_groups
# Creates all structural + functional + exempt
# account-level groups and their memberships
# ─────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.38.0"
    }
  }
}

# ── Exempt groups (cross-cutting) ─────────────

resource "databricks_group" "exempt" {
  provider     = databricks.account
  for_each     = toset(var.exempt_groups)
  display_name = each.value
  force        = true   # allow import if already exists
}

# ── Structural groups ─────────────────────────
# {env}_{domain}_{reader|writer|admin}

resource "databricks_group" "structural" {
  provider     = databricks.account
  for_each     = var.structural_groups_map
  display_name = each.value.name
  force        = true
}

# ── Functional groups — region scoped ─────────
# {env}_{domain}_{table}_region_{value}

resource "databricks_group" "region_scoped" {
  provider = databricks.account
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : [
          for region in var.region_values : {
            key    = "${var.environment}_${domain}_${tbl.table_name}_region_${region}"
            domain = domain
            table  = tbl.table_name
            region = region
          }
        ] if tbl.row_filter_type == "region_scoped"
      ]
    ]) : pair.key => pair
  }
  display_name = each.key
  force        = true
}

# ── Functional groups — entity scoped ─────────

resource "databricks_group" "entity_scoped" {
  provider = databricks.account
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : [
          for entity in var.entity_values : {
            key    = "${var.environment}_${domain}_${tbl.table_name}_${entity}"
            domain = domain
            table  = tbl.table_name
            entity = entity
          }
        ] if tbl.row_filter_type == "entity_scoped"
      ]
    ]) : pair.key => pair
  }
  display_name = each.key
  force        = true
}

# ── Functional groups — classification scoped ─

resource "databricks_group" "classification_scoped" {
  provider = databricks.account
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : [
          for cls in var.classification_values : {
            key    = "${var.environment}_${domain}_${tbl.table_name}_class_${cls}"
            domain = domain
            table  = tbl.table_name
            class  = cls
          }
        ] if tbl.row_filter_type == "classification"
      ]
    ]) : pair.key => pair
  }
  display_name = each.key
  force        = true
}

# ── Functional groups — PII access ────────────
# {env}_{domain}_{table}_pii_{clear|masked|none}

resource "databricks_group" "pii_access" {
  provider = databricks.account
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : [
          for access in var.pii_access_values : {
            key    = "${var.environment}_${domain}_${tbl.table_name}_${access}"
            domain = domain
            table  = tbl.table_name
            access = access
          }
        ] if length(tbl.pii_columns) > 0
      ]
    ]) : pair.key => pair
  }
  display_name = each.key
  force        = true
}

# ── Functional groups — financial access ──────

resource "databricks_group" "financial_access" {
  provider = databricks.account
  for_each = {
    for pair in flatten([
      for domain, tables in var.domain_tables : [
        for tbl in tables : [
          for access in var.financial_access_values : {
            key    = "${var.environment}_${domain}_${tbl.table_name}_${access}"
            domain = domain
            table  = tbl.table_name
            access = access
          }
        ] if length(tbl.financial_columns) > 0
      ]
    ]) : pair.key => pair
  }
  display_name = each.key
  force        = true
}

# ── Add pipeline SP to exempt groups ─────────

data "databricks_service_principal" "pipeline_sp" {
  provider     = databricks.account
  display_name = var.pipeline_exempt_sp_name
}

resource "databricks_group_member" "pipeline_sp_dlt_exempt" {
  provider  = databricks.account
  group_id  = databricks_group.exempt[var.dlt_pipeline_exempt_group].id
  member_id = data.databricks_service_principal.pipeline_sp.id
}
