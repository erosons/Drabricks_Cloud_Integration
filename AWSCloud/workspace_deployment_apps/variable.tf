
variable  "client_id" {
  description = "OAuth Client ID created in Databricks Account Console"
  type        = string
  default =  null
}

variable  "client_secret" {   
  description = "OAuth Client Secret created in Databricks Account Console"
  type        = string
  sensitive   = true
  default =  null
}

variable "databricks_account_id" {
  description = "Databricks Account ID"
  type        = string
 
}

variable "aws_region" {
  description = "AWS region to create resources in"
  type        = string
  default     = "us-east-1"
  
}