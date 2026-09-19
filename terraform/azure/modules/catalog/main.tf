# ─────────────────────────────────────────────
# Module: catalog
# Creates one Unity Catalog catalog per domain
# and assigns structural group USE privileges
# ─────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.38.0"
    }
  }
}

resource "databricks_catalog" "domain" {
  provider    = databricks.workspace
  name        = var.catalog_name   # e.g. prd_finance
  comment     = "Domain catalog for ${var.domain} in ${var.environment}"

  properties = {
    domain      = var.domain
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ── USE CATALOG granted to all structural groups for this domain ──

resource "databricks_grants" "catalog_use" {
  provider = databricks.workspace
  catalog  = databricks_catalog.domain.name

  dynamic "grant" {
    for_each = toset(["reader", "writer", "admin"])
    content {
      principal  = "${var.environment}_${var.domain}_${grant.value}"
      privileges = grant.value == "admin" ? ["USE_CATALOG", "CREATE_SCHEMA", "CREATE_TABLE"] : ["USE_CATALOG"]
    }
  }
}

# ── Default schema ────────────────────────────

resource "databricks_schema" "default_schemas" {
  provider     = databricks.workspace
  for_each     = toset(var.schemas)
  catalog_name = databricks_catalog.domain.name
  name         = each.value
  comment      = "Schema ${each.value} in ${var.catalog_name}"

  properties = {
    domain      = var.domain
    environment = var.environment
    schema      = each.value
    managed_by  = "terraform"
  }
}

# ── USE SCHEMA granted to structural groups ───

resource "databricks_grants" "schema_use" {
  provider = databricks.workspace
  for_each = toset(var.schemas)

  schema = "${databricks_catalog.domain.name}.${each.value}"

  dynamic "grant" {
    for_each = toset(["reader", "writer", "admin"])
    content {
      principal  = "${var.environment}_${var.domain}_${grant.value}"
      privileges = grant.value == "admin" ? ["USE_SCHEMA", "CREATE_TABLE", "CREATE_FUNCTION"] : ["USE_SCHEMA"]
    }
  }
}
