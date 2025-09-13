variable "aws_region" {
  description = "AWS region for the workspace"
  type        = string
  default     = "us-east-1"
}

variable "ami" {
  description = "Amazon machine image to use for ec2 instance"
  type        = string
  default     = "ami-011899242bb902164" # Ubuntu 20.04 LTS // us-east-1
}
# S3 Variables

variable "app_name" {
  description = "Name of the web application"
  type        = string
}

variable "environment_name" {
  description = "Deployment environment (dev/staging/production)"
  type        = string
}

variable "bucket_prefix" {
  description = "prefix of s3 bucket for app data"
  type        = string
}

# Route 53 Variables

variable "create_dns_zone" {
  description = "If true, create new route53 zone, if false read existing route53 zone"
  type        = bool
  default     = false
}

variable "domain" {
  description = "Domain for website"
  type        = string
}

variable "tags" {
  type        = map(string)
  description = "Additional tags applied to all resources created"
  default     = {}
}

variable "vpc_id" {
  description = "The VPC ID where resources will be deployed"
  type        = string
  default = "vpc-0ef86cd339eb0864b"
}

variable "instance_type" {
  description = "EC2 instance type for the web server"
  type        = string
  default     = "t3.micro"
}

# ###########################################################
# # Defining sensitive variables for database credentials
# ###########################################################

# variable "db_user" {
#   description = "Database username"
#   type        = string
#   sensitive = true
  
# }
# variable "db_password" {
#   description = "Database password"
#   type        = string
#   sensitive = true
# }