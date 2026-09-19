# ─────────────────────────────────────────────
# Root orchestration
# Instantiates all modules in dependency order:
#   1. access_groups  (account-level groups)
#   2. catalog        (one per domain per env)
#   3. row_filters    (functions in _policies schema)
#   4. column_masks   (functions in _policies schema)
#   5. table_grants   (SELECT + filter + mask attachment)
# ─────────────────────────────────────────────

# ── Step 1: Account-level groups ─────────────

module "access_groups" {
  source = "./modules/access_groups"

  providers = {
    databricks.account   = databricks.account
    databricks.workspace = databricks.workspace
  }

  environment             = var.environment
  exempt_groups           = local.exempt_groups
  structural_groups_map   = local.structural_groups_map
  domain_tables           = var.domain_tables
  region_values           = local.region_values
  entity_values           = local.entity_values
  classification_values   = local.classification_values
  pii_access_values       = local.pii_access_values
  financial_access_values = local.financial_access_values
  pipeline_exempt_sp_name = var.pipeline_exempt_sp_name
  dlt_pipeline_exempt_group = var.dlt_pipeline_exempt_group
  time_travel_exempt_group  = var.time_travel_exempt_group
}

# ── Step 2: Catalogs + schemas per domain ─────

module "catalog" {
  source   = "./modules/catalog"
  for_each = var.domain_tables   # one catalog per domain key

  providers = {
    databricks.workspace = databricks.workspace
  }

  environment  = var.environment
  domain       = each.key
  catalog_name = local.catalog_names[each.key]
  schemas      = distinct([for tbl in each.value : tbl.schema_name])

  depends_on = [module.access_groups]
}

# ── Step 3: Row filter functions ──────────────
# One module instance — creates functions across
# all domain tables in a given catalog.
# For multi-catalog setups, iterate per domain.

module "row_filters" {
  source   = "./modules/row_filters"
  for_each = var.domain_tables

  providers = {
    databricks.workspace = databricks.workspace
  }

  environment               = var.environment
  catalog_name              = local.catalog_names[each.key]
  domain_tables             = { (each.key) = each.value }
  domains_in_catalog        = [each.key]
  dlt_pipeline_exempt_group = var.dlt_pipeline_exempt_group
  time_travel_exempt_group  = var.time_travel_exempt_group

  depends_on = [module.catalog]
}

# ── Step 4: Column mask functions ─────────────

module "column_masks" {
  source   = "./modules/column_masks"
  for_each = var.domain_tables

  providers = {
    databricks.workspace = databricks.workspace
  }

  environment               = var.environment
  catalog_name              = local.catalog_names[each.key]
  domains_in_catalog        = [each.key]
  dlt_pipeline_exempt_group = var.dlt_pipeline_exempt_group
  time_travel_exempt_group  = var.time_travel_exempt_group

  depends_on = [module.catalog]
}

# ── Step 5: Table SELECT grants + filter/mask attachment ──

module "table_grants" {
  source   = "./modules/table_grants"
  for_each = var.domain_tables

  providers = {
    databricks.workspace = databricks.workspace
  }

  environment   = var.environment
  catalog_name  = local.catalog_names[each.key]
  domain_tables = { (each.key) = each.value }

  depends_on = [
    module.row_filters,
    module.column_masks,
  ]
}
