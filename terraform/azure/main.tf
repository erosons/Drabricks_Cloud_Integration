# =============================================================================
# RESOURCE GROUP
# =============================================================================

resource "azurerm_resource_group" "main" {
  name     = "${var.environment}-${var.project_name}-rg"
  location = var.location

  tags = merge(var.common_tags, {
    Environment = var.environment
    ManagedBy   = "Terraform"
  })
}

# =============================================================================
# NETWORKING
# =============================================================================

module "networking" {
  source = "./modules/networking"

  environment              = var.environment
  project_name             = var.project_name
  location                 = var.location
  resource_group_name      = azurerm_resource_group.main.name
  vnet_address_space       = var.vnet_address_space
  public_subnet_prefix     = var.public_subnet_prefix
  private_subnet_prefix    = var.private_subnet_prefix
  enable_private_endpoints = var.enable_private_endpoints
  common_tags              = var.common_tags
}

# =============================================================================
# STORAGE
# =============================================================================

module "storage" {
  source = "./modules/storage"

  environment                     = var.environment
  project_name                    = var.project_name
  location                        = var.location
  resource_group_name             = azurerm_resource_group.main.name
  storage_replication_type        = var.storage_replication_type
  storage_access_tier             = var.storage_access_tier
  enable_blob_versioning          = var.enable_blob_versioning
  enable_last_access_time         = var.enable_last_access_time
  blob_delete_retention_days      = var.blob_delete_retention_days
  container_delete_retention_days = var.container_delete_retention_days
  create_separate_data_storage    = var.create_separate_data_storage
  allowed_subnet_ids              = [module.networking.private_subnet_id]
  enable_private_endpoints        = var.enable_private_endpoints
  private_subnet_id               = module.networking.private_subnet_id
  # Pass the DNS zone *name* (e.g. "privatelink.blob.core.windows.net"), not the ARM ID
  blob_private_dns_zone_name      = module.networking.blob_private_dns_zone_name
  enable_cmk                      = var.enable_cmk
  metastore_container_name        = var.metastore_container_name
  data_container_name             = var.data_container_name
  common_tags                     = var.common_tags

  depends_on = [module.networking]
}

# =============================================================================
# DATABRICKS WORKSPACE
# =============================================================================

resource "azurerm_databricks_workspace" "main" {
  name                = "${var.environment}-${var.project_name}-workspace"
  location            = var.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = var.databricks_sku

  custom_parameters {
    virtual_network_id = module.networking.vnet_id
    subnet_name_public = module.networking.public_subnet_name
    subnet_name_private = module.networking.private_subnet_name
    # azurerm_databricks_workspace requires the NSG *association* resource ID, not the NSG ID
    public_subnet_network_security_group_association_id  = module.networking.public_nsg_association_id
    private_subnet_network_security_group_association_id = module.networking.private_nsg_association_id
  }

  tags = merge(var.common_tags, {
    Workspace = "${var.environment}-workspace"
  })

  depends_on = [module.networking]
}

# =============================================================================
# SERVICE PRINCIPAL FOR STORAGE ACCESS
# =============================================================================

resource "azuread_application" "databricks_sp" {
  display_name = "${var.environment}-${var.project_name}-databricks-sp"
}

resource "azuread_service_principal" "databricks_sp" {
  client_id = azuread_application.databricks_sp.client_id
}

resource "azuread_service_principal_password" "databricks_sp" {
  service_principal_id = azuread_service_principal.databricks_sp.object_id
  end_date             = timeadd(timestamp(), "8760h")

  lifecycle {
    ignore_changes = [end_date, start_date]
  }
}

resource "azurerm_role_assignment" "databricks_storage_contributor" {
  scope                = module.storage.metastore_storage_account_id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = azuread_service_principal.databricks_sp.object_id
}

# =============================================================================
# CLUSTER POLICIES
# =============================================================================

module "cluster_policies" {
  source = "./modules/cluster_policies"

  environment = var.environment

  create_prod_policy              = var.create_prod_policy
  prod_spark_version              = var.prod_spark_version
  prod_driver_node_type           = var.prod_driver_node_type
  prod_worker_node_type           = var.prod_worker_node_type
  prod_allowed_worker_types       = var.prod_allowed_worker_types
  prod_num_workers                = var.prod_num_workers
  prod_worker_range               = var.prod_worker_range
  prod_autotermination_minutes    = var.prod_autotermination_minutes
  prod_autotermination_range      = var.prod_autotermination_range
  prod_spark_conf                 = var.prod_spark_conf
  prod_init_scripts_path          = var.prod_init_scripts_path
  prod_log_path                   = var.prod_log_path

  create_staging_policy           = var.create_staging_policy
  staging_spark_version           = var.staging_spark_version
  staging_driver_node_type        = var.staging_driver_node_type
  staging_worker_node_type        = var.staging_worker_node_type
  staging_allowed_worker_types    = var.staging_allowed_worker_types
  staging_num_workers             = var.staging_num_workers
  staging_worker_range            = var.staging_worker_range
  staging_autotermination_minutes = var.staging_autotermination_minutes
  staging_autotermination_range   = var.staging_autotermination_range
  staging_spark_conf              = var.staging_spark_conf

  create_dev_policy               = var.create_dev_policy
  dev_spark_version               = var.dev_spark_version
  dev_driver_node_type            = var.dev_driver_node_type
  dev_worker_node_type            = var.dev_worker_node_type
  dev_allowed_worker_types        = var.dev_allowed_worker_types
  dev_num_workers                 = var.dev_num_workers
  dev_worker_range                = var.dev_worker_range
  dev_autotermination_minutes     = var.dev_autotermination_minutes
  dev_autotermination_range       = var.dev_autotermination_range

  create_sql_warehouse_policy       = var.create_sql_warehouse_policy
  warehouse_spark_version           = var.warehouse_spark_version
  warehouse_driver_node_type        = var.warehouse_driver_node_type
  warehouse_num_workers             = var.warehouse_num_workers
  warehouse_worker_range            = var.warehouse_worker_range
  warehouse_autotermination_minutes = var.warehouse_autotermination_minutes
  warehouse_autotermination_range   = var.warehouse_autotermination_range
  warehouse_spark_conf              = var.warehouse_spark_conf

  create_interactive_policy           = var.create_interactive_policy
  interactive_spark_version           = var.interactive_spark_version
  interactive_driver_node_type        = var.interactive_driver_node_type
  interactive_worker_node_type        = var.interactive_worker_node_type
  interactive_num_workers             = var.interactive_num_workers
  interactive_worker_range            = var.interactive_worker_range
  interactive_autotermination_minutes = var.interactive_autotermination_minutes
  interactive_autotermination_range   = var.interactive_autotermination_range

  create_job_policy    = var.create_job_policy
  job_spark_version    = var.job_spark_version
  job_driver_node_type = var.job_driver_node_type
  job_worker_node_type = var.job_worker_node_type
  job_num_workers      = var.job_num_workers

  depends_on = [azurerm_databricks_workspace.main]
}

# =============================================================================
# UNITY CATALOG METASTORE
# =============================================================================

resource "databricks_metastore" "main" {
  name         = "${var.environment}-metastore"
  storage_root = "abfss://${var.metastore_container_name}@${module.storage.metastore_storage_account_name}.dfs.core.windows.net/"
  region       = var.location
  comment      = "Unity Catalog metastore for ${var.environment}"

  depends_on = [module.storage, azurerm_databricks_workspace.main]
}

resource "databricks_metastore_assignment" "workspace" {
  workspace_id         = azurerm_databricks_workspace.main.workspace_id
  metastore_id         = databricks_metastore.main.metastore_id
  default_catalog_name = var.default_catalog_name
}

# =============================================================================
# STORAGE CREDENTIALS & EXTERNAL LOCATIONS
# =============================================================================

resource "databricks_storage_credential" "service_principal" {
  name = "${var.environment}-storage-credential"

  azure_service_principal {
    directory_id   = var.azure_tenant_id
    application_id = azuread_application.databricks_sp.client_id
    client_secret  = azuread_service_principal_password.databricks_sp.value
  }

  depends_on = [databricks_metastore.main]
}

resource "databricks_external_location" "metastore" {
  name          = "${var.environment}-metastore-location"
  url           = "abfss://${var.metastore_container_name}@${module.storage.metastore_storage_account_name}.dfs.core.windows.net/"
  credential_id = databricks_storage_credential.service_principal.id
  comment       = "External location for Unity Catalog metastore"

  depends_on = [databricks_storage_credential.service_principal]
}

resource "databricks_external_location" "data" {
  name          = "${var.environment}-data-location"
  url           = "abfss://${var.data_container_name}@${module.storage.metastore_storage_account_name}.dfs.core.windows.net/"
  credential_id = databricks_storage_credential.service_principal.id
  comment       = "External location for data"

  depends_on = [databricks_storage_credential.service_principal]
}
