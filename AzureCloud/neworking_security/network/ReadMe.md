VPC 10.0.0.0/16, DNS hostnames + resolution enabled

2 AZs (us-east-1a, us-east-1b)

2 public subnets, 4 private subnets (2 per AZ)

1 Internet Gateway

1 NAT Gateway (in 1 AZ) with EIP, used by all private subnets

S3 Gateway VPC Endpoint associated to private route tables

1 public route table + 2 private route tables