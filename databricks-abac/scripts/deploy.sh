#!/usr/bin/env bash
# ─────────────────────────────────────────────
# scripts/deploy.sh
# Deploy ABAC policies to a target environment.
# Usage:
#   ./scripts/deploy.sh prd plan
#   ./scripts/deploy.sh prd apply
#   ./scripts/deploy.sh dev plan
# ─────────────────────────────────────────────

set -euo pipefail

ENV="${1:-}"
ACTION="${2:-plan}"

if [[ -z "$ENV" ]]; then
  echo "Usage: $0 <dev|qa|uat|prd> <plan|apply|destroy>"
  exit 1
fi

if [[ ! "$ENV" =~ ^(dev|qa|uat|prd)$ ]]; then
  echo "ERROR: env must be one of: dev, qa, uat, prd"
  exit 1
fi

TFVARS_FILE="environments/${ENV}/${ENV}.tfvars"

if [[ ! -f "$TFVARS_FILE" ]]; then
  echo "ERROR: tfvars file not found: $TFVARS_FILE"
  exit 1
fi

echo "═══════════════════════════════════════"
echo "  Databricks ABAC — ${ENV} — ${ACTION}"
echo "═══════════════════════════════════════"

# Secrets injected from vault / CI env vars
export TF_VAR_databricks_account_client_id="${DATABRICKS_ACCOUNT_CLIENT_ID}"
export TF_VAR_databricks_account_client_secret="${DATABRICKS_ACCOUNT_CLIENT_SECRET}"
export TF_VAR_databricks_workspace_client_id="${DATABRICKS_WORKSPACE_CLIENT_ID}"
export TF_VAR_databricks_workspace_client_secret="${DATABRICKS_WORKSPACE_CLIENT_SECRET}"

terraform init \
  -backend-config="key=databricks-abac/${ENV}/terraform.tfstate" \
  -reconfigure

terraform "$ACTION" \
  -var-file="$TFVARS_FILE" \
  ${ACTION == "apply" ? "-auto-approve" : ""} \
  -compact-warnings

echo "Done: ${ENV} ${ACTION} complete"
