
resource "databricks_mws_ncc_private_endpoint_rule" "storage" {
  provider                       = databricks.account
  network_connectivity_config_id = databricks_mws_network_connectivity_config.ncc.network_connectivity_config_id
  endpoint_service               = "com.amazonaws.us-east-1.s3"
  resource_names                 = ["bucket"]
}

resource "databricks_mws_ncc_private_endpoint_rule" "vpce" {
  provider                       = databricks.account
  network_connectivity_config_id = databricks_mws_network_connectivity_config.ncc.network_connectivity_config_id
  endpoint_service               = "com.amazonaws.vpce.us-west-2.vpce-svc-xyz"
  domain_names                   = ["subdomain.internal.net"]
}