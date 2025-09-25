# Workspace VPC
resource "aws_vpc" "ws" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = merge(var.tags, { Name = "${var.name_prefix}-ws-vpc" })
}

resource "aws_subnet" "ws_private" {
  vpc_id                  = aws_vpc.ws.id
  cidr_block              = var.ws_private_subnet_cidr
  map_public_ip_on_launch = false
  tags = merge(var.tags, { Name = "${var.name_prefix}-ws-private" })
}

resource "aws_subnet" "ws_pe" {
  vpc_id                  = aws_vpc.ws.id
  cidr_block              = var.ws_pe_subnet_cidr
  map_public_ip_on_launch = false
  tags = merge(var.tags, { Name = "${var.name_prefix}-ws-pe" })
}

# Transit VPC
resource "aws_vpc" "transit" {
  cidr_block           = var.transit_vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true
  tags = merge(var.tags, { Name = "${var.name_prefix}-transit-vpc" })
}

resource "aws_subnet" "transit_pe" {
  vpc_id                  = aws_vpc.transit.id
  cidr_block              = var.transit_pe_subnet_cidr
  map_public_ip_on_launch = false
  tags = merge(var.tags, { Name = "${var.name_prefix}-transit-pe" })
}

# Security groups (minimal allowlists per Databricks doc)
# Workspace SG used by clusters/subnets
resource "aws_security_group" "workspace" {
  name        = "${var.name_prefix}-workspace-sg"
  description = "Databricks workspace SG"
  vpc_id      = aws_vpc.ws.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  tags = var.tags
}

# Backend endpoints SG (SCC relay needs 6666; workspace REST/API needs 443, 8443-8451, etc.)
resource "aws_security_group" "backend" {
  name        = "${var.name_prefix}-backend-vpce-sg"
  description = "For SCC relay & workspace VPCEs"
  vpc_id      = aws_vpc.ws.id

  # Allow from workspace subnets
  ingress { from_port = 443  to_port = 443  protocol = "tcp" cidr_blocks = [aws_vpc.ws.cidr_block] }
  ingress { from_port = 6666 to_port = 6666 protocol = "tcp" cidr_blocks = [aws_vpc.ws.cidr_block] }
  ingress { from_port = 8443 to_port = 8451 protocol = "tcp" cidr_blocks = [aws_vpc.ws.cidr_block] }

  egress  { from_port = 0 to_port = 0 protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
  tags = var.tags
}

# Front-end endpoint SG (UI/API over 443 from transit VPC/on-prem)
resource "aws_security_group" "frontend" {
  name        = "${var.name_prefix}-frontend-vpce-sg"
  description = "For front-end VPCE"
  vpc_id      = aws_vpc.transit.id

  ingress { from_port = 443 to_port = 443 protocol = "tcp" cidr_blocks = [aws_vpc.transit.cidr_block] }
  egress  { from_port = 0   to_port = 0   protocol = "-1" cidr_blocks = ["0.0.0.0/0"] }
  tags = var.tags
}
