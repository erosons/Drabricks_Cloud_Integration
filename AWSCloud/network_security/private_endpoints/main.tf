# Back-end Workspace VPCE (REST/API)
resource "aws_vpc_endpoint" "backend_workspace" {
  vpc_id              = var.workspace_vpc_id
  service_name        = var.svc_name_workspace
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids          = [var.backend_subnet_id]
  security_group_ids  = [var.backend_sg_id]
  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-workspace" })
}

# Back-end SCC Relay VPCE (port 6666)
resource "aws_vpc_endpoint" "backend_scc" {
  vpc_id              = var.workspace_vpc_id
  service_name        = var.svc_name_scc_relay
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids          = [var.backend_subnet_id]
  security_group_ids  = [var.backend_sg_id]
  tags = merge(var.tags, { Name = "${var.name_prefix}-backend-scc" })
}

# Front-end VPCE (UI/API) in transit VPC
resource "aws_vpc_endpoint" "frontend" {
  vpc_id              = var.transit_vpc_id
  service_name        = var.svc_name_workspace   # front-end uses the Workspace service
  vpc_endpoint_type   = "Interface"
  private_dns_enabled = true

  subnet_ids          = [var.frontend_subnet_id]
  security_group_ids  = [var.frontend_sg_id]
  tags = merge(var.tags, { Name = "${var.name_prefix}-frontend" })
}
