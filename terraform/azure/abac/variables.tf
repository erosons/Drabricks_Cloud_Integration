# ─────────────────────────────────────────────
# Global variables — set per environment via tfvars
# ─────────────────────────────────────────────

variable "databricks_account_id" {
  type        = string
  description = "Databricks account ID (found in account console)"
}

variable "databricks_account_client_id" {
  type        = string
  description = "Service principal client_id with account-level admin"
  sensitive   = true
}

variable "databricks_account_client_secret" {
  type        = string
  description = "Service principal client_secret (account-level)"
  sensitive   = true
}

variable "databricks_workspace_url" {
  type        = string
  description = "Workspace URL e.g. https://adb-123456789.0.azuredatabricks.net"
}

variable "databricks_workspace_client_id" {
  type        = string
  description = "Service principal client_id with workspace admin"
  sensitive   = true
}

variable "databricks_workspace_client_secret" {
  type        = string
  sensitive   = true
}

variable "environment" {
  type        = string
  description = "Deployment environment: dev | qa | uat | prd"
  validation {
    condition     = contains(["dev", "qa", "uat", "prd"], var.environment)
    error_message = "environment must be one of: dev, qa, uat, prd"
  }
}

variable "domains" {
  type        = list(string)
  description = "List of data domain names — one catalog will be created per domain per env"
  default = [
    "finance",
    "risk",
    "hr",
    "operations",
    "marketing"
    # extend to all 40 domains here
  ]
}

variable "pipeline_exempt_sp_name" {
  type        = string
  description = "Display name of the DLT pipeline service principal (exempt from all filters)"
}

variable "time_travel_exempt_group" {
  type        = string
  description = "Account group name whose members bypass row filters for time travel / audit"
  default     = "time_travel_exempt"
}

variable "dlt_pipeline_exempt_group" {
  type        = string
  description = "Account group name whose members bypass row filters for DLT pipeline reads"
  default     = "dlt_pipeline_exempt"
}

# ─────────────────────────────────────────────
# Per-domain table definitions
# Consumed by filter + grant modules
# ─────────────────────────────────────────────

variable "domain_tables" {
  description = "Map of domain → table configs. Each table declares its filter archetypes and PII columns."
  type = map(list(object({
    table_name       = string
    schema_name      = string
    row_filter_type  = string       # "region_scoped" | "entity_scoped" | "date_range" | "classification" | "none"
    row_filter_col   = string       # column used for row-level filtering (e.g. "region", "org_id")
    pii_columns      = list(string) # columns that receive col_mask_pii
    financial_columns = list(string) # columns that receive col_mask_financial
  })))

  default = {
    finance = [
      {
        table_name        = "ledger"
        schema_name       = "core"
        row_filter_type   = "region_scoped"
        row_filter_col    = "region"
        pii_columns       = ["customer_name", "customer_email", "tax_id"]
        financial_columns = ["amount", "balance", "credit_limit"]
      },
      {
        table_name        = "transactions"
        schema_name       = "core"
        row_filter_type   = "entity_scoped"
        row_filter_col    = "business_unit_id"
        pii_columns       = ["account_holder"]
        financial_columns = ["transaction_amount"]
      }
    ]
    risk = [
      {
        table_name        = "exposure"
        schema_name       = "core"
        row_filter_type   = "classification"
        row_filter_col    = "data_classification"
        pii_columns       = []
        financial_columns = ["notional_value", "mtm_value"]
      }
    ]
  }
}
