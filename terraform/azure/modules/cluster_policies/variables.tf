variable "environment" {
  description = "Environment name (prod, staging, dev)"
  type        = string
}

# -----------------------------------------------------------------------------
# Production policy
# -----------------------------------------------------------------------------

variable "create_prod_policy" {
  description = "Create the production cluster policy"
  type        = bool
  default     = true
}

variable "prod_spark_version" {
  description = "Spark runtime version for production clusters"
  type        = string
  default     = "14.3.x-scala2.12"
}

variable "prod_driver_node_type" {
  description = "Driver node VM type for production clusters"
  type        = string
  default     = "Standard_DS4_v2"
}

variable "prod_worker_node_type" {
  description = "Default worker node VM type for production clusters"
  type        = string
  default     = "Standard_DS4_v2"
}

variable "prod_allowed_worker_types" {
  description = "Allowed worker node VM types for production clusters"
  type        = list(string)
  default     = ["Standard_DS4_v2", "Standard_DS5_v2"]
}

variable "prod_num_workers" {
  description = "Default number of workers for production clusters"
  type        = number
  default     = 4
}

variable "prod_worker_range" {
  description = "Min and max workers for production clusters [min, max]"
  type        = list(number)
  default     = [2, 8]
}

variable "prod_autotermination_minutes" {
  description = "Default autotermination minutes for production clusters"
  type        = number
  default     = 60
}

variable "prod_autotermination_range" {
  description = "Min and max autotermination minutes for production clusters [min, max]"
  type        = list(number)
  default     = [30, 120]
}

variable "prod_spark_conf" {
  description = "Spark configuration for production clusters"
  type        = map(string)
  default     = {}
}

variable "prod_init_scripts_path" {
  description = "DBFS path to init scripts for production clusters"
  type        = string
  default     = "dbfs:/init-scripts/prod"
}

variable "prod_log_path" {
  description = "DBFS path for cluster logs for production clusters"
  type        = string
  default     = "dbfs:/cluster-logs/prod"
}

# -----------------------------------------------------------------------------
# Staging policy
# -----------------------------------------------------------------------------

variable "create_staging_policy" {
  description = "Create the staging cluster policy"
  type        = bool
  default     = true
}

variable "staging_spark_version" {
  description = "Spark runtime version for staging clusters"
  type        = string
  default     = "14.3.x-scala2.12"
}

variable "staging_driver_node_type" {
  description = "Driver node VM type for staging clusters"
  type        = string
  default     = "Standard_DS3_v2"
}

variable "staging_worker_node_type" {
  description = "Default worker node VM type for staging clusters"
  type        = string
  default     = "Standard_DS3_v2"
}

variable "staging_allowed_worker_types" {
  description = "Allowed worker node VM types for staging clusters"
  type        = list(string)
  default     = ["Standard_DS3_v2", "Standard_DS4_v2"]
}

variable "staging_num_workers" {
  description = "Default number of workers for staging clusters"
  type        = number
  default     = 2
}

variable "staging_worker_range" {
  description = "Min and max workers for staging clusters [min, max]"
  type        = list(number)
  default     = [1, 4]
}

variable "staging_autotermination_minutes" {
  description = "Default autotermination minutes for staging clusters"
  type        = number
  default     = 30
}

variable "staging_autotermination_range" {
  description = "Min and max autotermination minutes for staging clusters [min, max]"
  type        = list(number)
  default     = [15, 60]
}

variable "staging_spark_conf" {
  description = "Spark configuration for staging clusters"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# Development policy
# -----------------------------------------------------------------------------

variable "create_dev_policy" {
  description = "Create the development cluster policy"
  type        = bool
  default     = true
}

variable "dev_spark_version" {
  description = "Spark runtime version for development clusters"
  type        = string
  default     = "14.3.x-scala2.12"
}

variable "dev_driver_node_type" {
  description = "Driver node VM type for development clusters"
  type        = string
  default     = "Standard_DS3_v2"
}

variable "dev_worker_node_type" {
  description = "Default worker node VM type for development clusters"
  type        = string
  default     = "Standard_DS3_v2"
}

variable "dev_allowed_worker_types" {
  description = "Allowed worker node VM types for development clusters"
  type        = list(string)
  default     = ["Standard_DS3_v2", "Standard_DS4_v2", "Standard_F4s_v2"]
}

variable "dev_num_workers" {
  description = "Default number of workers for development clusters"
  type        = number
  default     = 1
}

variable "dev_worker_range" {
  description = "Min and max workers for development clusters [min, max]"
  type        = list(number)
  default     = [0, 4]
}

variable "dev_autotermination_minutes" {
  description = "Default autotermination minutes for development clusters"
  type        = number
  default     = 20
}

variable "dev_autotermination_range" {
  description = "Min and max autotermination minutes for development clusters [min, max]"
  type        = list(number)
  default     = [10, 60]
}

# -----------------------------------------------------------------------------
# SQL Warehouse policy
# -----------------------------------------------------------------------------

variable "create_sql_warehouse_policy" {
  description = "Create the SQL Warehouse cluster policy"
  type        = bool
  default     = true
}

variable "warehouse_spark_version" {
  description = "Spark runtime version for SQL Warehouse clusters"
  type        = string
  default     = "14.3.x-scala2.12"
}

variable "warehouse_driver_node_type" {
  description = "Driver node VM type for SQL Warehouse clusters"
  type        = string
  default     = "Standard_DS4_v2"
}

variable "warehouse_num_workers" {
  description = "Default number of workers for SQL Warehouse clusters"
  type        = number
  default     = 2
}

variable "warehouse_worker_range" {
  description = "Min and max workers for SQL Warehouse clusters [min, max]"
  type        = list(number)
  default     = [1, 6]
}

variable "warehouse_autotermination_minutes" {
  description = "Default autotermination minutes for SQL Warehouse clusters"
  type        = number
  default     = 30
}

variable "warehouse_autotermination_range" {
  description = "Min and max autotermination minutes for SQL Warehouse clusters [min, max]"
  type        = list(number)
  default     = [10, 60]
}

variable "warehouse_spark_conf" {
  description = "Spark configuration for SQL Warehouse clusters"
  type        = map(string)
  default     = {}
}

# -----------------------------------------------------------------------------
# Interactive policy
# -----------------------------------------------------------------------------

variable "create_interactive_policy" {
  description = "Create the interactive cluster policy"
  type        = bool
  default     = true
}

variable "interactive_spark_version" {
  description = "Spark runtime version for interactive clusters"
  type        = string
  default     = "14.3.x-scala2.12"
}

variable "interactive_driver_node_type" {
  description = "Driver node VM type for interactive clusters"
  type        = string
  default     = "Standard_DS3_v2"
}

variable "interactive_worker_node_type" {
  description = "Worker node VM type for interactive clusters"
  type        = string
  default     = "Standard_DS3_v2"
}

variable "interactive_num_workers" {
  description = "Default number of workers for interactive clusters"
  type        = number
  default     = 2
}

variable "interactive_worker_range" {
  description = "Min and max workers for interactive clusters [min, max]"
  type        = list(number)
  default     = [1, 4]
}

variable "interactive_autotermination_minutes" {
  description = "Default autotermination minutes for interactive clusters"
  type        = number
  default     = 30
}

variable "interactive_autotermination_range" {
  description = "Min and max autotermination minutes for interactive clusters [min, max]"
  type        = list(number)
  default     = [15, 60]
}

# -----------------------------------------------------------------------------
# Job policy
# -----------------------------------------------------------------------------

variable "create_job_policy" {
  description = "Create the job cluster policy"
  type        = bool
  default     = true
}

variable "job_spark_version" {
  description = "Spark runtime version for job clusters"
  type        = string
  default     = "14.3.x-scala2.12"
}

variable "job_driver_node_type" {
  description = "Driver node VM type for job clusters"
  type        = string
  default     = "Standard_DS4_v2"
}

variable "job_worker_node_type" {
  description = "Worker node VM type for job clusters"
  type        = string
  default     = "Standard_DS4_v2"
}

variable "job_num_workers" {
  description = "Fixed number of workers for job clusters"
  type        = number
  default     = 4
}
