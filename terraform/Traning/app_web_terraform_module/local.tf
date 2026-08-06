# Pick one subnet (first). Optionally choose by AZ instead.
locals {
  chosen_subnet_id = data.aws_subnets.default.ids[0]
  all_subnet_ids = data.aws_subnets.default.ids
}

locals {
  # Group: AZ => [subnet_ids...]
  public_subnets_by_az = {
    for s in data.aws_subnet.public_each :
    s.availability_zone => s.id...
  }

  # Deterministically choose ONE subnet per AZ
  # (sort keys for stable order; pick the lowest-id subnet in each AZ)
  alb_subnets = [
    for az in sort(keys(local.public_subnets_by_az)) :
    sort(local.public_subnets_by_az[az])[0]
  ]
}