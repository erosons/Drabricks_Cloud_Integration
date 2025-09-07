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
  security_group_ids = [var.security_group_ids]
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