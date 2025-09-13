data "aws_vpc" "default" {
  id = var.vpc_id
}

data "aws_subnets" "default" {
 filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# data "aws_security_group" "default" {
#   name = "default"
#   vpc_id = data.aws_vpc.default.id
# }

resource "aws_security_group" "default" {
  name        =  "${var.app_name}-${var.environment_name}-instance-security-group"
  description = "Allow all inbound and outbound traffic"
  vpc_id      = data.aws_vpc.default.id  # replace with your VPC id, or pass as a variable

  # Inbound: allow everything
  ingress {
    description = "Allow all inbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  # Outbound: allow everything
  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = var.tags
}


