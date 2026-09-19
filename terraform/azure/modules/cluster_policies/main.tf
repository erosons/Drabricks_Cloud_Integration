terraform {
  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.0"
    }
  }
}

resource "databricks_cluster_policy" "production" {
  count       = var.create_prod_policy ? 1 : 0
  name        = "${var.environment}-production-policy"
  description = "Production cluster policy with strict controls"
  definition = jsonencode({
    cluster_type = {
      type  = "fixed"
      value = "all-purpose"
    }
    spark_version = {
      type  = "fixed"
      value = var.prod_spark_version
    }
    driver_node_type_id = {
      type  = "fixed"
      value = var.prod_driver_node_type
    }
    worker_node_type_id = {
      type         = "allowlist"
      values       = var.prod_allowed_worker_types
      defaultValue = var.prod_worker_node_type
    }
    num_workers = {
      type         = "range"
      defaultValue = var.prod_num_workers
      minValue     = var.prod_worker_range[0]
      maxValue     = var.prod_worker_range[1]
    }
    autotermination_minutes = {
      type         = "range"
      defaultValue = var.prod_autotermination_minutes
      minValue     = var.prod_autotermination_range[0]
      maxValue     = var.prod_autotermination_range[1]
    }
    enable_elastic_disk = {
      type  = "fixed"
      value = true
    }
    "spark_conf.spark.databricks.cluster.profile" = {
      type  = "fixed"
      value = "serverless"
    }
    cluster_log_conf = {
      dbfs = {
        destination = var.prod_log_path
      }
    }
    init_scripts = [{
      dbfs = {
        destination = var.prod_init_scripts_path
      }
    }]
  })
}

resource "databricks_cluster_policy" "staging" {
  count       = var.create_staging_policy ? 1 : 0
  name        = "${var.environment}-staging-policy"
  description = "Staging cluster policy with balanced controls"
  definition = jsonencode({
    cluster_type = {
      type  = "fixed"
      value = "all-purpose"
    }
    spark_version = {
      type  = "fixed"
      value = var.staging_spark_version
    }
    driver_node_type_id = {
      type  = "fixed"
      value = var.staging_driver_node_type
    }
    worker_node_type_id = {
      type         = "allowlist"
      values       = var.staging_allowed_worker_types
      defaultValue = var.staging_worker_node_type
    }
    num_workers = {
      type         = "range"
      defaultValue = var.staging_num_workers
      minValue     = var.staging_worker_range[0]
      maxValue     = var.staging_worker_range[1]
    }
    autotermination_minutes = {
      type         = "range"
      defaultValue = var.staging_autotermination_minutes
      minValue     = var.staging_autotermination_range[0]
      maxValue     = var.staging_autotermination_range[1]
    }
    enable_elastic_disk = {
      type  = "fixed"
      value = true
    }
  })
}

resource "databricks_cluster_policy" "development" {
  count       = var.create_dev_policy ? 1 : 0
  name        = "${var.environment}-development-policy"
  description = "Development cluster policy with flexible controls"
  definition = jsonencode({
    cluster_type = {
      type  = "fixed"
      value = "all-purpose"
    }
    spark_version = {
      type  = "fixed"
      value = var.dev_spark_version
    }
    driver_node_type_id = {
      type  = "fixed"
      value = var.dev_driver_node_type
    }
    worker_node_type_id = {
      type         = "allowlist"
      values       = var.dev_allowed_worker_types
      defaultValue = var.dev_worker_node_type
    }
    num_workers = {
      type         = "range"
      defaultValue = var.dev_num_workers
      minValue     = var.dev_worker_range[0]
      maxValue     = var.dev_worker_range[1]
    }
    autotermination_minutes = {
      type         = "range"
      defaultValue = var.dev_autotermination_minutes
      minValue     = var.dev_autotermination_range[0]
      maxValue     = var.dev_autotermination_range[1]
    }
    enable_elastic_disk = {
      type  = "fixed"
      value = true
    }
  })
}

resource "databricks_cluster_policy" "sql_warehouse" {
  count       = var.create_sql_warehouse_policy ? 1 : 0
  name        = "${var.environment}-sql-warehouse-policy"
  description = "SQL Warehouse cluster policy for analytics"
  definition = jsonencode({
    cluster_type = {
      type  = "fixed"
      value = "all-purpose"
    }
    spark_version = {
      type  = "fixed"
      value = var.warehouse_spark_version
    }
    driver_node_type_id = {
      type  = "fixed"
      value = var.warehouse_driver_node_type
    }
    num_workers = {
      type         = "range"
      defaultValue = var.warehouse_num_workers
      minValue     = var.warehouse_worker_range[0]
      maxValue     = var.warehouse_worker_range[1]
    }
    autotermination_minutes = {
      type         = "range"
      defaultValue = var.warehouse_autotermination_minutes
      minValue     = var.warehouse_autotermination_range[0]
      maxValue     = var.warehouse_autotermination_range[1]
    }
  })
}

resource "databricks_cluster_policy" "interactive" {
  count       = var.create_interactive_policy ? 1 : 0
  name        = "${var.environment}-interactive-policy"
  description = "Interactive cluster policy for data scientists"
  definition = jsonencode({
    cluster_type = {
      type  = "fixed"
      value = "all-purpose"
    }
    spark_version = {
      type  = "fixed"
      value = var.interactive_spark_version
    }
    driver_node_type_id = {
      type  = "fixed"
      value = var.interactive_driver_node_type
    }
    worker_node_type_id = {
      type  = "fixed"
      value = var.interactive_worker_node_type
    }
    num_workers = {
      type         = "range"
      defaultValue = var.interactive_num_workers
      minValue     = var.interactive_worker_range[0]
      maxValue     = var.interactive_worker_range[1]
    }
    autotermination_minutes = {
      type         = "range"
      defaultValue = var.interactive_autotermination_minutes
      minValue     = var.interactive_autotermination_range[0]
      maxValue     = var.interactive_autotermination_range[1]
    }
  })
}

resource "databricks_cluster_policy" "job" {
  count       = var.create_job_policy ? 1 : 0
  name        = "${var.environment}-job-policy"
  description = "Job cluster policy for automated workloads"
  definition = jsonencode({
    cluster_type = {
      type  = "fixed"
      value = "job"
    }
    spark_version = {
      type  = "fixed"
      value = var.job_spark_version
    }
    driver_node_type_id = {
      type  = "fixed"
      value = var.job_driver_node_type
    }
    worker_node_type_id = {
      type  = "fixed"
      value = var.job_worker_node_type
    }
    num_workers = {
      type  = "fixed"
      value = var.job_num_workers
    }
    autotermination_minutes = {
      type  = "fixed"
      value = 0
      hidden = true
    }
  })
}
