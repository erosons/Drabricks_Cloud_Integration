#### 🔹 Locals Block
locals {
  newbits          = 8
  azs              = var.azs
  public_count     = length(local.azs)
  private_per_az   = 2
  private_count    = local.private_per_az * length(local.azs)

  public_idx_range  = toset([for i in range(local.public_count) : i])
  private_idx_range = toset([for i in range(local.private_count) : i])

  private_az_for_idx = [for i in local.private_idx_range : local.azs[i % length(local.azs)]]
}

idx=0 → us-east-1a
idx=1 → us-east-1b
idx=2 → us-east-1a
idx=3 → us-east-1b

### 🔹 Public Subnets

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

### 🔹 Private Subnets
resource "aws_subnet" "private" {
  for_each = { for i in local.private_idx_range : i => {
    az  = local.private_az_for_idx[i]
    idx = i + local.public_count
  } }

  vpc_id            = aws_vpc.this.id
  availability_zone = each.value.az
  cidr_block        = cidrsubnet(var.vpc_cidr, local.newbits, each.value.idx)

  tags = {
    Name = "${var.name}-subnet-private${(tonumber(each.key) % local.private_per_az) + 1}-${each.value.az}"
    Tier = "private"
  }
}

#### Route Table Associations
resource "aws_route_table_association" "private_assoc" {
  for_each = aws_subnet.private
  subnet_id      = each.value.id
  route_table_id = aws_route_table.private[each.value.availability_zone].id
}


Iterates over all private subnets.

Each subnet is linked to the private RT of its AZ.


### #🔹 S3 VPC Endpoint
resource "aws_vpc_endpoint" "s3" {
  vpc_id       = aws_vpc.this.id
  service_name = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"

  route_table_ids = [for rt in aws_route_table.private : rt.id]
}


[for rt in aws_route_table.private : rt.id]
→ list comprehension → [rtb-private-us-east-1a-id, rtb-private-us-east-1b-id].

✅ When to Use Loops in Terraform

Use loops (for_each, count, or for comprehensions) when:

Resource repetition is needed (e.g., multiple subnets, AZs, or route tables).

Dynamic mapping is required (e.g., one subnet per AZ, but AZ list is variable).

Scalability: You want adding/removing AZs to auto-adjust infra without rewriting.

👉 In this VPC:

Public subnets loop over AZ list.

Private subnets loop over AZs × count per AZ.

Associations loop over subnets to bind them to correct RT.

Endpoint loops over private RTs.