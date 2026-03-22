
##########################################
# PRIVATE DNS (Route53) FOR PRIVATELINK
##########################################
# Resolving DNS vpc name to IP privately
# Private zone that shadows the public one *inside your VPC*
resource "aws_route53_zone" "cloud_dbx" {
  name = "cloud.databricks.com"
  vpc  { vpc_id = aws_vpc.this.id }
}

# Get host from the workspace your child module creates
locals {
  workspace_fqdn = trimsuffix(
                     replace(replace(databricks_mws_workspaces.this.workspace_url, "https://",""), "http://",""),
                   "/")

}

# Workspace URL  -> Workspace VPCE
resource "aws_route53_record" "dbx_workspace_priv" {
  zone_id = aws_route53_zone.cloud_dbx.zone_id
  name    = local.workspace_fqdn                         # e.g., dbc-xxxx.cloud.databricks.com
  type    = "CNAME"
  ttl     = 60
  records = [aws_vpc_endpoint.dbl_workspace.dns_entry[0].dns_name]
}

# Backend host -> Backend VPCE (SCC relay)
resource "aws_route53_record" "dbx_backend_priv" {
  zone_id = aws_route53_zone.cloud_dbx.zone_id
  name    = local.dbx_backend_host                       # tunnel.privatelink.us-east-1.cloud.databricks.com
  type    = "CNAME"
  ttl     = 60
  records = [aws_vpc_endpoint.dbl_backend.dns_entry[0].dns_name]
}
