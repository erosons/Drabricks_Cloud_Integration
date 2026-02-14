variable "aws_region" {
  description = "AWS region to deploy resources"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (e.g., production, staging, dev)"
  type        = string
  default     = "production"
}

variable "github_token" {
  description = "GitHub Personal Access Token with repo and admin:org scopes"
  type        = string
  sensitive   = true
}

variable "github_org" {
  description = "GitHub organization name"
  type        = string
}

variable "github_repo" {
  description = "GitHub repository name"
  type        = string
}

variable "runner_count" {
  description = "Number of runner instances to create"
  type        = number
  default     = 1
}

variable "instance_type" {
  description = "EC2 instance type"
  type        = string
  default     = "t3.large"
}

variable "root_volume_size" {
  description = "Root volume size in GB"
  type        = number
  default     = 50
}

variable "ssh_allowed_cidrs" {
  description = "CIDR blocks allowed to SSH into runners"
  type        = list(string)
  default     = [] # Empty = no SSH access
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key file"
  type        = string
  default     = "~/.ssh/github-runner-key.pub"
}

variable "custom_labels" {
  description = "Additional custom labels for the runner"
  type        = list(string)
  default     = []
}

variable "runner_group" {
  description = "Runner group name (Default if not specified)"
  type        = string
  default     = "Default"
}