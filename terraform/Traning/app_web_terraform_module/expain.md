1. aws_route53_zone "primary" (Resource Block)
resource "aws_route53_zone" "primary" {
  count = var.create_dns_zone ? 1 : 0
  name  = var.domain
}


#### Purpose: Creates a new Route53 hosted zone if var.create_dns_zone is true.

count argument:

If var.create_dns_zone = true, count = 1, so Terraform creates the zone.

If var.create_dns_zone = false, count = 0, so Terraform skips creation.

Indexing: Because of count, the resource is referenced as aws_route53_zone.primary[0] when created.

2. data "aws_route53_zone" "primary" (Data Block)
data "aws_route53_zone" "primary" {
  count = var.create_dns_zone ? 0 : 1
  name  = var.domain
}


##### Purpose: Looks up an existing Route53 hosted zone if var.create_dns_zone is false.

count:

If var.create_dns_zone = true, count = 0 (skip lookup).

If var.create_dns_zone = false, count = 1 (lookup the existing zone).

Indexing: Referenced as data.aws_route53_zone.primary[0] when used.

3. Locals Block
locals {
  dns_zone_id = var.create_dns_zone ? aws_route53_zone.primary[0].zone_id : data.aws_route53_zone.primary[0].zone_id
  subdomain   = var.environment_name == "production" ? "" : "${var.environment_name}."
}


dns_zone_id:

##### If Terraform created the zone → use aws_route53_zone.primary[0].zone_id.

If Terraform only looked up the zone → use data.aws_route53_zone.primary[0].zone_id.
👉 This creates a single variable (local.dns_zone_id) that always holds the right zone ID regardless of whether it was created or fetched.

subdomain:

If environment = "production" → use an empty string (root domain, e.g., example.com).

Otherwise → prefix with environment name, e.g. "dev.example.com", "qa.example.com".