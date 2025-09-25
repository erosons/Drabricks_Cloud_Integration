# A record: <deployment>.cloud.databricks.com -> VPCE private IP

# The A + CNAME above are exactly what Databricks’ front-end PrivateLink 
# DNS page requires (map <deployment>.cloud.databricks.com to your front-end VPCE IP, and CNAME dbc-dp-<workspace-id> to your <deployment> host).

resource "aws_route53_record" "workspace_a" {
  zone_id = var.zone_id
  name    = var.workspace_hostname
  type    = "A"
  ttl     = 60
  records = [var.frontend_vpce_ip]
}

# CNAME: dbc-dp-<workspace-id>.cloud.databricks.com -> <deployment>.cloud.databricks.com
resource "aws_route53_record" "dbc_dp_cname" {
  zone_id = var.zone_id
  name    = "dbc-dp-${var.workspace_id}.cloud.databricks.com"
  type    = "CNAME"
  ttl     = 60
  records = [var.workspace_hostname]
}


