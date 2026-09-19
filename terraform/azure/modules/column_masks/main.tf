# ─────────────────────────────────────────────
# Module: column_masks
# Deploys column mask functions for PII and
# financial columns. Functions live in the
# _policies schema and are referenced by
# ALTER TABLE ... ALTER COLUMN SET MASK
# ─────────────────────────────────────────────

terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = ">= 1.38.0"
    }
  }
}

# ── PII column mask ───────────────────────────
# Created once per domain (not per table) —
# referenced by all tables in the catalog that
# have PII columns.
#
# Outputs:
#   pii_clear   → original value
#   pii_masked  → SHA-256 hash of value
#   pii_none    → NULL (no value visible)

resource "databricks_sql_function" "col_mask_pii" {
  provider     = databricks.workspace
  for_each     = toset(var.domains_in_catalog)

  name         = "col_mask_pii_${each.value}"
  catalog_name = var.catalog_name
  schema_name  = "_policies"
  input_params {
    name      = "col_value"
    type_text = "STRING"
  }
  return_type { type_text = "STRING" }
  routine_body = "SQL"
  body = <<-SQL
    CASE
      -- Exempt tiers always see clear value
      WHEN is_account_group_member('${var.dlt_pipeline_exempt_group}')  THEN col_value
      WHEN is_account_group_member('${var.time_travel_exempt_group}')   THEN col_value
      WHEN is_account_group_member('${var.environment}_${each.value}_admin') THEN col_value
      -- Functional: per-table PII access levels
      -- (reader gets masked by default unless in pii_clear group)
      WHEN is_account_group_member('${var.environment}_${each.value}_pii_clear_global')  THEN col_value
      WHEN is_account_group_member('${var.environment}_${each.value}_pii_masked_global') THEN sha2(col_value, 256)
      -- Default: no PII visible
      ELSE NULL
    END
  SQL
  comment = "PII column mask for domain ${each.value}. Managed by Terraform."
}

# ── Financial column mask ─────────────────────
# Masks sensitive numeric columns for users
# without explicit financial_clear access

resource "databricks_sql_function" "col_mask_financial" {
  provider     = databricks.workspace
  for_each     = toset(var.domains_in_catalog)

  name         = "col_mask_financial_${each.value}"
  catalog_name = var.catalog_name
  schema_name  = "_policies"
  input_params {
    name      = "col_value"
    type_text = "DECIMAL(38,10)"
  }
  return_type { type_text = "DECIMAL(38,10)" }
  routine_body = "SQL"
  body = <<-SQL
    CASE
      WHEN is_account_group_member('${var.dlt_pipeline_exempt_group}')   THEN col_value
      WHEN is_account_group_member('${var.time_travel_exempt_group}')    THEN col_value
      WHEN is_account_group_member('${var.environment}_${each.value}_admin')            THEN col_value
      WHEN is_account_group_member('${var.environment}_${each.value}_financial_clear')  THEN col_value
      WHEN is_account_group_member('${var.environment}_${each.value}_financial_masked') THEN ROUND(col_value, -3)
      ELSE NULL
    END
  SQL
  comment = "Financial sensitivity column mask for domain ${each.value}. Managed by Terraform."
}

# ── EXECUTE grants on mask functions ──────────

resource "databricks_grants" "col_mask_pii_execute" {
  provider = databricks.workspace
  for_each = toset(var.domains_in_catalog)

  function = "${var.catalog_name}._policies.col_mask_pii_${each.value}"

  dynamic "grant" {
    for_each = toset(["reader", "writer"])
    content {
      principal  = "${var.environment}_${each.value}_${grant.value}"
      privileges = ["EXECUTE"]
    }
  }

  depends_on = [databricks_sql_function.col_mask_pii]
}

resource "databricks_grants" "col_mask_financial_execute" {
  provider = databricks.workspace
  for_each = toset(var.domains_in_catalog)

  function = "${var.catalog_name}._policies.col_mask_financial_${each.value}"

  dynamic "grant" {
    for_each = toset(["reader", "writer"])
    content {
      principal  = "${var.environment}_${each.value}_${grant.value}"
      privileges = ["EXECUTE"]
    }
  }

  depends_on = [databricks_sql_function.col_mask_financial]
}
