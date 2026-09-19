resource "databricks_mws_vpc_endpoint" "backend_workspace" {
  account_id       = var.account_id
  aws_vpc_endpoint_id = var.vpce_id_backend_workspace
  region           = var.aws_region
  name             = "${var.name_prefix}-backend-workspace"
}

resource "databricks_mws_vpc_endpoint" "backend_scc" {
  account_id       = var.account_id
  aws_vpc_endpoint_id = var.vpce_id_backend_scc
  region           = var.aws_region
  name             = "${var.name_prefix}-backend-scc"
}

# 2) Create Private Access Settings (front-end control)
resource "databricks_mws_private_access_settings" "pas" {
  account_id  = var.account_id
  region      = var.aws_region
  name        = "${var.name_prefix}-pas"

  # whether public ingress is allowed alongside PrivateLink
  public_access_enabled = var.private_access_public_enabled

  # Restrict who can connect:
  private_access_level = var.private_access_level
  allowed_vpc_endpoint_ids = var.private_access_level == "ENDPOINT"
    ? [databricks_mws_vpc_endpoint.frontend.vpc_endpoint_id]
    : null
}

# 3) Network config for back-end (SCC relay + workspace)
resource "databricks_mws_networks" "net" {
  account_id         = var.account_id
  network_name       = "${var.name_prefix}-netcfg"
  region             = var.aws_region
  vpc_id             = var.workspace_vpc_id
  subnet_ids         = var.workspace_subnet_ids
  security_group_ids = [var.workspace_security_group_id]

  backend_rest_vpc_endpoint_id = databricks_mws_vpc_endpoint.backend_workspace.vpc_endpoint_id
  backend_relay_vpc_endpoint_id = databricks_mws_vpc_endpoint.backend_scc.vpc_endpoint_id
}

# Datbricks managed policies are used to create cross-account IAM role and policy
# # Attach Databricks-managed policy with required permissions
data "databricks_aws_crossaccount_policy" "this" {
}

data "databricks_aws_assume_role_policy" "this" {
  external_id = var.databricks_account_id
}

# # Bucket policy that lets the Databricks role access the root bucket
data "databricks_aws_bucket_policy" "this" {
  bucket   = aws_s3_bucket.root.bucket
  provider = databricks.mws
}


# Register the IAM role (credentials) at the Databricks ACCOUNT level
#  The represent Access connector in Azure, which has data reader role on storage account
resource "databricks_mws_credentials" "this" {
  provider         = databricks.mws
  credentials_name = "${local.prefix}-creds"
  role_arn         = aws_iam_role.cross_account_role.arn
    depends_on = [time_sleep.wait_30_seconds]
}

# Mapping the Access connector/storage credential acess to S3 bucket which will be used as DBFS root
resource "databricks_mws_storage_configurations" "this" {
  provider                   = databricks.mws
  account_id                 = var.databricks_account_id
  storage_configuration_name = "${local.prefix}-storage"
  bucket_name                = aws_s3_bucket.root.bucket

  depends_on = [ databricks_mws_credentials.this , aws_s3_bucket_policy.root_bucket_policy]
}

# provisioning VPC and Subnets for Databricks workspace

// register VPC
resource "databricks_mws_networks" "this" {
  provider           = databricks.mws
  account_id         = var.databricks_account_id
  network_name       = "${var.network_prefix}-network"
  vpc_id             = var.vpc_id
  subnet_ids         = var.subnets_private_ids
  security_group_ids = var.security_group_ids
  private_access_settings_id = databricks_mws_private_access_settings.pas.private_access_settings_id
  pricing_tier      = "ENTERPRISE"
}


# Provisioning Databricks Workspace
resource "databricks_mws_workspaces" "this" {
  provider       = databricks.mws
  account_id     = var.databricks_account_id
  workspace_name = local.prefix
  aws_region     = var.aws_region

  credentials_id           = databricks_mws_credentials.this.credentials_id
  storage_configuration_id = databricks_mws_storage_configurations.this.storage_configuration_id
  network_id               = databricks_mws_networks.this.network_id

  # Optional Custom Tags
  custom_tags = var.tags
  depends_on = [ databricks_mws_networks.this ,
                 time_sleep.wait_30_seconds ,
                 databricks_mws_credentials.this, 
                 databricks_mws_storage_configurations.this 
                 ]

}