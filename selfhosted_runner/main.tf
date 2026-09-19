terraform {
  required_version = ">= 1.0"
  
  required_providers {
    github = {
      source  = "integrations/github"
      version = "~> 6.0"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Configure providers
provider "aws" {
  region = var.aws_region
}

provider "github" {
  token = var.github_token
  owner = var.github_org
}

# Get registration token from GitHub API
data "github_actions_registration_token" "runner" {
  repository = var.github_repo
}

# Get latest Ubuntu AMI
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Create VPC (optional - use existing VPC if you have one)
resource "aws_vpc" "runner_vpc" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = {
    Name        = "github-runner-vpc"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

# Create subnet
resource "aws_subnet" "runner_subnet" {
  vpc_id                  = aws_vpc.runner_vpc.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true

  tags = {
    Name        = "github-runner-subnet"
    Environment = var.environment
  }
}

# Internet Gateway
resource "aws_internet_gateway" "runner_igw" {
  vpc_id = aws_vpc.runner_vpc.id

  tags = {
    Name        = "github-runner-igw"
    Environment = var.environment
  }
}

# Route table
resource "aws_route_table" "runner_rt" {
  vpc_id = aws_vpc.runner_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.runner_igw.id
  }

  tags = {
    Name        = "github-runner-rt"
    Environment = var.environment
  }
}

# Route table association
resource "aws_route_table_association" "runner_rta" {
  subnet_id      = aws_subnet.runner_subnet.id
  route_table_id = aws_route_table.runner_rt.id
}

# Security group
resource "aws_security_group" "runner_sg" {
  name        = "github-runner-sg"
  description = "Security group for GitHub Actions runners"
  vpc_id      = aws_vpc.runner_vpc.id

  # Allow outbound internet access (needed for GitHub API, package downloads, etc.)
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "Allow all outbound traffic"
  }

  # SSH access (optional - for debugging)
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.ssh_allowed_cidrs
    description = "SSH access"
  }

  tags = {
    Name        = "github-runner-sg"
    Environment = var.environment
  }
}

# IAM role for EC2 instance (if you need AWS permissions)
resource "aws_iam_role" "runner_role" {
  name = "github-runner-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "github-runner-role"
    Environment = var.environment
  }
}

# Attach policies (example: allow ECR access, S3, etc.)
resource "aws_iam_role_policy_attachment" "ecr_read" {
  role       = aws_iam_role.runner_role.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

# Instance profile
resource "aws_iam_instance_profile" "runner_profile" {
  name = "github-runner-profile-${var.environment}"
  role = aws_iam_role.runner_role.name
}

# SSH Key pair (create one first: ssh-keygen -t rsa -b 4096 -f github-runner-key)
resource "aws_key_pair" "runner_key" {
  key_name   = "github-runner-key-${var.environment}"
  public_key = file(var.ssh_public_key_path)
}

# EC2 Instance - GitHub Runner
resource "aws_instance" "github_runner" {
  count = var.runner_count

  ami           = data.aws_ami.ubuntu.id
  instance_type = var.instance_type
  
  subnet_id                   = aws_subnet.runner_subnet.id
  vpc_security_group_ids      = [aws_security_group.runner_sg.id]
  iam_instance_profile        = aws_iam_instance_profile.runner_profile.name
  key_name                    = aws_key_pair.runner_key.key_name
  associate_public_ip_address = true

  # User data to configure runner
  user_data = templatefile("${path.module}/setup-runner.sh", {
    github_url    = "https://github.com/${var.github_org}/${var.github_repo}"
    runner_token  = data.github_actions_registration_token.runner.token
    runner_name   = "runner-${var.environment}-${count.index + 1}"
    runner_labels = join(",", concat(["aws", "terraform-managed", var.environment], var.custom_labels))
    runner_group  = var.runner_group
  })

  # Storage
  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    delete_on_termination = true
    encrypted             = true
  }

  # Metadata options (security best practice)
  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  tags = {
    Name        = "github-runner-${var.environment}-${count.index + 1}"
    Environment = var.environment
    ManagedBy   = "terraform"
    Purpose     = "github-actions-runner"
  }

  # Wait for instance to be ready
  lifecycle {
    create_before_destroy = true
  }
}