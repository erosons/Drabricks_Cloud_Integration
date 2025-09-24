terraform {
  required_version = ">= 1.6.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  # We’ll carve /24s out of the /16 for all subnets
  # (newbits = 8 => /16 + 8 = /24). You can change to /20 etc. by reducing newbits.
  newbits          = 8
  azs              = var.azs
  public_count     = length(local.azs)                # 1 public per AZ
  private_per_az   = 2                                # 2 priv per AZ (total 4)
  private_count    = local.private_per_az * length(local.azs)

  # Index helpers
  public_idx_range  = toset([for i in range(local.public_count) : i])
  private_idx_range = toset([for i in range(local.private_count) : i])

  # Spread private subnets evenly across AZs (round-robin)
  private_az_for_idx = [for i in local.private_idx_range : local.azs[i % length(local.azs)]]
}

# ---------------- VPC ----------------
resource "aws_vpc" "this" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = {
    Name = "${var.name}-vpc"
  }
}

# Internet Gateway
resource "aws_internet_gateway" "this" {
  vpc_id = aws_vpc.this.id
  tags = { Name = "${var.name}-igw" }
}

# ---------------- Subnets ----------------
# Public subnets (one per AZ)
resource "aws_subnet" "public" {
  for_each = { for i, az in local.azs : i => { az = az, idx = i } }

  vpc_id                  = aws_vpc.this.id
  availability_zone       = each.value.az
  cidr_block              = cidrsubnet(var.vpc_cidr, local.newbits, each.value.idx)
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.name}-subnet-public-${each.value.az}"
    Tier = "public"
  }
}

# Private subnets (2 per AZ => total 4)
resource "aws_subnet" "private" {
  for_each = { for i in local.private_idx_range : i => {
    az  = local.private_az_for_idx[i]
    idx = i + local.public_count            # continue indexing after public range
  } }

  vpc_id            = aws_vpc.this.id
  availability_zone = each.value.az
  cidr_block        = cidrsubnet(var.vpc_cidr, local.newbits, each.value.idx)

  tags = {
    Name = "${var.name}-subnet-private${(tonumber(each.key) % local.private_per_az) + 1}-${each.value.az}"
    Tier = "private"
  }
}

# ---------------- NAT (1 in 1 AZ) ----------------
# Allocate EIP for NAT
resource "aws_eip" "nat" {
  domain = "vpc"
  tags = { Name = "${var.name}-eip-nat" }
}

# Put the NAT in the first AZ’s public subnet
locals {
  nat_az        = local.azs[0]
  nat_public_id = aws_subnet.public[0].id
}

resource "aws_nat_gateway" "this" {
  allocation_id = aws_eip.nat.id
  subnet_id     = local.nat_public_id
  tags = { Name = "${var.name}-nat-${local.nat_az}" }
  depends_on = [aws_internet_gateway.this]
}

# ---------------- Route Tables ----------------
# 1) Public RT with default route to IGW
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.this.id
  tags = { Name = "${var.name}-rtb-public" }
}

resource "aws_route" "public_inet" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.this.id
}

# Associate all public subnets to public RT
resource "aws_route_table_association" "public_assoc" {
  for_each       = aws_subnet.public
  subnet_id      = each.value.id
  route_table_id = aws_route_table.public.id
}

# 2) Private RTs (one per AZ) that point to the single NAT gateway
resource "aws_route_table" "private" {
  for_each = { for az in local.azs : az => az }
  vpc_id   = aws_vpc.this.id
  tags = { Name = "${var.name}-rtb-private-${each.key}" }
}

resource "aws_route" "private_to_nat" {
  for_each                = aws_route_table.private
  route_table_id          = each.value.id
  destination_cidr_block  = "0.0.0.0/0"
  nat_gateway_id          = aws_nat_gateway.this.id
}

# Associate private subnets to RT of their AZ
resource "aws_route_table_association" "private_assoc" {
  for_each = aws_subnet.private
  subnet_id = each.value.id
  route_table_id = aws_route_table.private[each.value.availability_zone].id
}

# ---------------- S3 Gateway Endpoint (attach to private RTs) ----------------
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.this.id
  service_name = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = [for rt in aws_route_table.private : rt.id]

  tags = { Name = "${var.name}-vpce-s3" }
}
