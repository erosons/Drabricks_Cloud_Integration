############################
# VPC & PRIVATE SUBNETS ONLY
# https://docs.databricks.com/aws/en/resources/ip-domain-region
# https://docs.databricks.com/aws/en/security/network/classic/customer-managed-vpc
############################
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "${var.environment}-vpc" }
}

# Private subnets (one per AZ)
resource "aws_subnet" "private" {
  for_each          = { for idx, az in var.azs : idx => { az = az, cidr = var.private_cidrs[idx] } }
  vpc_id            = aws_vpc.this.id
  cidr_block        = each.value.cidr
  availability_zone = each.value.az
  tags = { Name = "${var.environment}-private-${each.value.az}" }
}

# Private route tables (NO 0.0.0.0/0 route since there is no IGW/NAT)
resource "aws_route_table" "private" {
  for_each = aws_subnet.private
  vpc_id   = aws_vpc.this.id
  tags     = { Name = "${var.environment}-rtb-private-${each.value.availability_zone}" }
}

resource "aws_route_table_association" "private_assoc" {
  for_each       = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.key].id
}

#################################
# CORE VPC ENDPOINT SG- FIREWALL
#################################

resource "aws_security_group" "allow_tls" {
  name        = "allow_tls"
  description = "Allow TLS inbound traffic and all outbound traffic"
  vpc_id      = aws_vpc.this.id

  tags = {
    Name = "allow_tls"
  }

}
locals { 
  ws_ports_single = [8443, 8444] 
  }

resource "aws_vpc_security_group_ingress_rule" "allow_tls_ipv4" {
  security_group_id = aws_security_group.allow_tls.id
  cidr_ipv4         = aws_vpc.this.cidr_block
  from_port         = 443
  ip_protocol       = "tcp"
  to_port           = 443

}


resource "aws_vpc_security_group_ingress_rule" "ws_single" {
   for_each                    = toset([for p in local.ws_ports_single : tostring(p)])
  security_group_id            = aws_security_group.allow_tls.id
  cidr_ipv4                    = aws_vpc.this.cidr_block
  ip_protocol                  = "tcp"
  from_port                   = tonumber(each.key)
  to_port                      = tonumber(each.key)
  description                  = "Databricks Workspace PL port ${each.key} from cluster SG"
}

# reserved range 8445–8451
resource "aws_vpc_security_group_ingress_rule" "ws_reserved_range" {
  security_group_id            = aws_security_group.allow_tls.id
  cidr_ipv4                    = aws_vpc.this.cidr_block
  ip_protocol                  = "tcp"
  from_port                    = 8445
  to_port                      = 8451
  description                  = "Databricks Workspace reserved ports"
}

# SG already attached to your interface endpoints
resource "aws_vpc_security_group_ingress_rule" "vpce_backend_6666" {
  security_group_id = aws_security_group.allow_tls.id   # the SG on the VPCE ENIs
  from_port         = 6666
  to_port           = 6666
  ip_protocol          = "tcp"
  cidr_ipv4         = var.vpc_cidr                      # or source_security_group_id for tighter scope
  description       = "Databricks SCC relay (PrivateLink) port"
}


resource "aws_vpc_security_group_egress_rule" "allow_all_traffic_ipv4" {
# By default, AWS creates an ALLOW ALL egress rule when creating a new
#  Security Group inside of a VPC. When creating a new Security Group inside a VPC,
#   Terraform will remove this default rule, and require you specifically re-create
#    it if you desire that rule. We feel this leads to fewer surprises in terms of
#     controlling your egress rules. If you desire this rule to be in place, you can use this egress block:
  security_group_id = aws_security_group.allow_tls.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "-1" # semantically equivalent to all ports
}

############################################
# S3 GATEWAY ENDPOINT (for DBFS / root bucket)
############################################
resource "aws_vpc_endpoint" "s3_gateway" {
  vpc_id            = aws_vpc.this.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"
  # Attach to PRIVATE route tables so private subnets reach S3 without internet/NAT
  route_table_ids   = [for _, r in aws_route_table.private : r.id]
  tags = { Name = "${var.environment}-vpce-s3" }
}

###############################
# INTERFACE ENDPOINTS FOR BOOT
###############################
# STS is required if there is no NAT egress (instance creds/token exchange)
# Target AWS STS in your region (e.g., com.amazonaws.us-east-1.sts).
# Databricks nodes (and lots of AWS SDKs) call STS to get/refresh temporary credentials. Without NAT, this endpoint is essential.
resource "aws_vpc_endpoint" "sts" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.aws_region}.sts"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [for _, s in aws_subnet.private : s.id]
  security_group_ids  = [aws_security_group.allow_tls.id]  # Firewall
  private_dns_enabled = true
  tags = { Name = "${var.environment}-vpce-sts" }
}

# CloudWatch Logs for bootstrap/log shipping without internet
resource "aws_vpc_endpoint" "logs" {
  vpc_id              = aws_vpc.this.id
  service_name        = "com.amazonaws.${var.aws_region}.logs"
  vpc_endpoint_type   = "Interface"
  subnet_ids          = [for _, s in aws_subnet.private : s.id]
  security_group_ids  = [aws_security_group.allow_tls.id]  #Firewall
  private_dns_enabled = true
  tags = { Name = "${var.environment}-vpce-logs" }
}


###############################
# ---------------- Transit Gateway (optional) ----------------
# VPC -VPC PEERING PRIVATELY
###############################
resource "aws_ec2_transit_gateway" "tgw" {
  count = var.tgw_create ? 1 : 0
  description = "${var.environment}-tgw"
  amazon_side_asn = 64512
  default_route_table_association = "enable"
  default_route_table_propagation = "enable"
  tags = { Name = "${var.environment}-tgw" }
}

resource "aws_ec2_transit_gateway_vpc_attachment" "tgw_attach" {
  count              = var.tgw_create ? 1 : 0
  transit_gateway_id = aws_ec2_transit_gateway.tgw[0].id
  vpc_id             = aws_vpc.this.id
  subnet_ids         = [for _, s in aws_subnet.private : s.id]
  dns_support        = "enable"
  ipv6_support       = "disable"
  appliance_mode_support = "disable"
  tags = { Name = "${var.environment}-tgw-att" }
}

# Example: route the peer CIDR via TGW in *private* RTBs
resource "aws_route" "to_tgw" {
  for_each = var.tgw_create ? aws_route_table.private : {}
  route_table_id         = each.value.id
  destination_cidr_block = var.tgw_peer_cidr
  transit_gateway_id     = aws_ec2_transit_gateway.tgw[0].id
}