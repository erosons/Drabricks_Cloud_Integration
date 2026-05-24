###############################################
# DATABRICKS PRIVATELINK (Workspace + Backend)

###############################################

locals {

  # Databricks PrivateLink endpoint service names (per region table)
  dbx_workspace_service = "com.amazonaws.vpce.us-east-1.vpce-svc-09143d1e626de2f04" # Workspace (incl. REST)
  dbx_backend_service   = "com.amazonaws.vpce.us-east-1.vpce-svc-00018a8c3ff62ffdf" # SCC relay

  # Backend hostname to map via DNS
  dbx_backend_host = var.privatelink_tunnel_host
}


# Endpoint	               What it’s for	                                                                                                 Without it…
# Workspace (UI/API)	  Private access for users, REST API, CLI, DBSQL, notebook web traffic into the Databricks control plane.	             You can’t reach the workspace UI/API privately (you’d need public egress).
# Backend	              Private, bidirectional control-plane ↔ cluster communications (jobs status, artifacts, driver heartbeats, notebook commands, etc.).  Clusters can’t fully “phone home”; they hang/spin even if EC2 is running.
# Databricks notes the “Workspace (including REST API)” service is used for both front-end and back-end REST calls; you still need the SCC relay endpoint separately
resource "aws_vpc_endpoint" "dbl_workspace" {
  vpc_id              = aws_vpc.this.id
  service_name        = local.dbx_workspace_service
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [for _, s in aws_subnet.private : s.id]
  security_group_ids  = [aws_security_group.allow_tls.id]
  private_dns_enabled = false  # Use your PHZ to point to these endpoints
  tags = { Name = "${var.environment}-vpce-dbx-workspace" }
}

resource "aws_vpc_endpoint" "dbl_backend" {
  vpc_id              = aws_vpc.this.id
  service_name        = local.dbx_backend_service
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [for _, s in aws_subnet.private : s.id]
  security_group_ids  = [aws_security_group.allow_tls.id]
  private_dns_enabled = false
  tags = { Name = "${var.environment}-vpce-dbx-backend" }
}



# After aws_vpc_endpoint.dbl_workspace / dbl_backend are created…

resource "databricks_mws_vpc_endpoint" "ws" {
  provider           = databricks.mws
  account_id         = var.databricks_account_id
  vpc_endpoint_name  = "${var.environment}-ws"
  aws_vpc_endpoint_id= aws_vpc_endpoint.dbl_workspace.id
  region             = var.aws_region
 depends_on = [ aws_vpc_endpoint.dbl_workspace ]
}

resource "databricks_mws_vpc_endpoint" "scc" {
  provider            = databricks.mws
  account_id          = var.databricks_account_id
  vpc_endpoint_name   = "${var.environment}-scc"
  aws_vpc_endpoint_id = aws_vpc_endpoint.dbl_backend.id
  region              = var.aws_region
  depends_on = [ aws_vpc_endpoint.dbl_backend ]
}

resource "databricks_mws_private_access_settings" "pas" {
  provider                       = databricks.mws
  private_access_settings_name   = "pas-${var.environment}"
  region                         = var.aws_region
  public_access_enabled          = true
  private_access_level         = "ENDPOINT"
  # Newer provider versions expose this allow-list:
  allowed_vpc_endpoint_ids = [
    databricks_mws_vpc_endpoint.ws.vpc_endpoint_id
  ]
}