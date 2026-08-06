terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ── Latest Amazon Linux 2023 AMI ────────────────────────────────────────────
data "aws_ami" "al2023" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-2023.*-x86_64"]
  }
  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# ── Default VPC & subnets ────────────────────────────────────────────────────
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# ── Security Group ───────────────────────────────────────────────────────────
resource "aws_security_group" "kraken_bot" {
  name        = "${var.project_name}-sg"
  description = "Kraken AI trading bot - SSH + full egress"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "SSH"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # Grafana dashboard (optional)
  ingress {
    description = "Grafana"
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # Prometheus metrics (optional)
  ingress {
    description = "Prometheus"
    from_port   = 9090
    to_port     = 9090
    protocol    = "tcp"
    cidr_blocks = [var.allowed_ssh_cidr]
  }

  # Full egress — bot needs outbound to Kraken WS + REST
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name        = "${var.project_name}-sg"
    Environment = var.environment
    Project     = var.project_name
  }
}

# ── EC2 Instance ─────────────────────────────────────────────────────────────
# m5n.large: 2 vCPU | 8 GiB RAM | up to 25 Gbps ENA (Enhanced Networking)
resource "aws_instance" "kraken_bot" {
  ami                    = data.aws_ami.al2023.id
  instance_type          = var.instance_type
  key_name               = var.key_pair_name
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.kraken_bot.id]

  # Placement group = lower latency within the same AZ
  placement_group = aws_placement_group.kraken_bot.id

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 30
    throughput            = 250 # MB/s — gp3 max is 1000 MB/s
    iops                  = 4000
    delete_on_termination = true
    encrypted             = true

    tags = {
      Name = "${var.project_name}-root"
    }
  }

  user_data                   = file("${path.module}/user_data.sh")
  user_data_replace_on_change = true

  monitoring = true # CloudWatch detailed monitoring

  tags = {
    Name        = "${var.project_name}-${var.environment}"
    Environment = var.environment
    Project     = var.project_name
  }

  lifecycle {
    ignore_changes = [ami] # don't replace instance on AMI updates
  }
}

# Cluster placement group for lowest latency
resource "aws_placement_group" "kraken_bot" {
  name     = "${var.project_name}-pg"
  strategy = "cluster"

  tags = {
    Name    = "${var.project_name}-pg"
    Project = var.project_name
  }
}

# ── Elastic IP — stable address across restarts ──────────────────────────────
resource "aws_eip" "kraken_bot" {
  domain = "vpc"

  tags = {
    Name        = "${var.project_name}-eip"
    Environment = var.environment
    Project     = var.project_name
  }
}

resource "aws_eip_association" "kraken_bot" {
  instance_id   = aws_instance.kraken_bot.id
  allocation_id = aws_eip.kraken_bot.id
}
