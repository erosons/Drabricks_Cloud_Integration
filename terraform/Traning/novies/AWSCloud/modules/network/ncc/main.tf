variable "region" {}
variable "prefix" {}

resource "databricks_mws_network_connectivity_config" "ncc" {
  provider = databricks.account
  name     = "ncc-for-${var.prefix}"
  region   = var.region
}

resource "databricks_mws_ncc_binding" "ncc_binding" {
  provider                       = databricks.account
  network_connectivity_config_id = databricks_mws_network_connectivity_config.ncc.network_connectivity_config_id
  workspace_id                   = var.databricks_workspace_id
  depends_on = [ workspace provisoning ]
}