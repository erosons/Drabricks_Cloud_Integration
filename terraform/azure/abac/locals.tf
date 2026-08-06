# ─────────────────────────────────────────────
# Naming conventions and derived locals
# All resource names flow from here — change
# the convention once and it propagates everywhere
# ─────────────────────────────────────────────

locals {
  env = var.environment

  # Catalog name pattern:  {env}_{domain}
  catalog_names = {
    for domain in var.domains :
    domain => "${local.env}_${domain}"
  }

  # ── Structural group names ──────────────────
  # Pattern: {env}_{domain}_{role}
  # Roles: reader | writer | admin
  structural_group_roles = ["reader", "writer", "admin"]

  structural_groups = flatten([
    for domain in var.domains : [
      for role in local.structural_group_roles : {
        key    = "${local.env}_${domain}_${role}"
        domain = domain
        role   = role
        name   = "${local.env}_${domain}_${role}"
      }
    ]
  ])

  structural_groups_map = {
    for g in local.structural_groups : g.key => g
  }

  # ── Functional group names ──────────────────
  # Row-filter dimension groups per table
  # Pattern: {env}_{domain}_{table}_{dimension}_{value}

  region_values     = ["apac", "emea", "amer", "global"]
  entity_values     = ["bu_retail", "bu_wholesale", "bu_corporate", "all_entities"]
  classification_values = ["public", "internal", "confidential", "restricted"]
  pii_access_values = ["pii_clear", "pii_masked", "pii_none"]
  financial_access_values = ["financial_clear", "financial_masked"]

  # Exempt groups — no domain or table scope
  exempt_groups = [
    var.time_travel_exempt_group,
    var.dlt_pipeline_exempt_group,
  ]

  # ── Tag definitions for column policy automation ──
  # Tables tagged with these will have masks auto-applied
  pii_tag_key        = "pii"
  pii_tag_value      = "true"
  financial_tag_key  = "sensitivity"
  financial_tag_value = "financial"
}
