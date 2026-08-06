variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "instance_type" {
  description = "EC2 instance type. m5n.large = 8 GiB RAM, 2 vCPU, up to 25 Gbps ENA"
  type        = string
  default     = "m5n.large"

  validation {
    condition = contains([
      "m5n.large", "m5n.xlarge",   # 8/16 GiB, 25 Gbps ENA
      "c5n.xlarge", "c5n.2xlarge", # compute-optimised, 25 Gbps
      "r5n.large",                  # memory-optimised, 25 Gbps
    ], var.instance_type)
    error_message = "Choose an 'n' family instance for enhanced network throughput."
  }
}

variable "key_pair_name" {
  description = "Name of an existing EC2 key pair to use for SSH access"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR allowed to SSH and access dashboards (e.g. your home IP /32)"
  type        = string
  default     = "0.0.0.0/0"
}

variable "project_name" {
  description = "Prefix used for all resource names and tags"
  type        = string
  default     = "kraken-bot"
}

variable "environment" {
  description = "Deployment environment tag"
  type        = string
  default     = "production"

  validation {
    condition     = contains(["production", "staging", "development"], var.environment)
    error_message = "environment must be production, staging, or development."
  }
}
