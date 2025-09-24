locals {
  environments = ["dev", "test", "uat"]
}

module "dbx_workspace" {
  source   = "../workspace_module"
  for_each = toset(local.environments)

   # 👇 child uses account-level resources with provider = databricks.mws
   providers = {
    databricks.mws = databricks.mws
  }

    aws_region                    = "us-east-1"
    workspace_name_prefix         = "dbx-databricks-wk-${each.key}"
    access_connector_prefix       = "dbx-access-connector-${each.key}"
    bucket_name_prefix            = "dbx-bucket-${each.key}"
    tf_backend_bucket             = "dbx-backend-tf-${each.key}"
    dynamodb_table_name           = "dbx-remote-state-lock"
    databricks_account_id         = var.databricks_account_id
    vpc_id                        = "vpc-0f80ef0a48b036fe8"
    network_prefix                = "dbx-network-${each.key}"
    subnets_private_ids           = ["subnet-0f0beef3de5e7fa66","subnet-058abd6ad47cdfe3c"]
    security_group_ids            = "sg-0c04dbd290b14cf7c"
    client_id                     = var.client_id
    client_secret                 = var.client_secret
    //aad_groups              = ["account_unity_admin", "data_engineer", "data_analyst", "data_scientist"]
    tags = {
    "Project" = "POC"
    "Environment" = each.key
    "Owner" = "Samson"
    }


}


# module "dbx_workspace_test" {
#    source = "../workspace_module"

#     providers = {
#     databricks= databricks.mws
#   }

#     aws_region                    = "us-east-1"
#     workspace_name_prefix         = "dbx-databricks-wk-test"
#     access_connector_prefix       = "dbx-access-connector-test"
#     bucket_name_prefix            = "dbx-bucket-test"
#     tf_backend_bucket             = "dbx-backend-tf-test"
#     dynamodb_table_name           = "dbx-remote-state-lock"
#     databricks_account_id         = "67690736-ed9f-4566-9c09-6ce4af6eb2e3"
#     vpc_id                        = "vpc-0f80ef0a48b036fe8"
#     network_prefix                = "dbx-network-test"
#     subnets_private_ids           = ["subnet-0f0beef3de5e7fa66","subnet-058abd6ad47cdfe3c"]
#     security_group_ids            = "sg-0c04dbd290b14cf7c"
#     client_id                     = var.client_id
#     client_secret                 = var.client_secret
#     //aad_groups              = ["account_unity_admin", "data_engineer", "data_analyst", "data_scientist"]
#     tags = {
#     "Project" = "POC"
#     "Environment" = "test"
#     "Owner" = "Samson"
#     }


# }


# module "dbx_workspace_prd" {
#    source = "../workspace_module"

#    providers = {
#     databricks = databricks.prd
#    }

#     aws_region                    = "us-east-1"
#     workspace_name_prefix         = "dbx-databricks-wk-prd"
#     access_connector_prefix       = "dbx-access-connector-prd"
#     bucket_name_prefix            = "dbx-bucket-prd"
#     tf_backend_bucket             = "dbx-backend-tf-prd"
#     dynamodb_table_name           = "dbx-remote-state-lock"
#     databricks_account_id         = "67690736-ed9f-4566-9c09-6ce4af6eb2e3"
#     vpc_id                        = "vpc-0f80ef0a48b036fe8"
#     network_prefix                = "dbx-network-prd"
#     subnets_private_ids           = ["subnet-0f0beef3de5e7fa66","subnet-058abd6ad47cdfe3c"]
#     security_group_ids            = "sg-0c04dbd290b14cf7c"
#     client_id                     = var.client_id
#     client_secret                 = var.client_secret
#     //aad_groups              = ["account_unity_admin", "data_engineer", "data_analyst", "data_scientist"]
#     tags = {
#     "Project" = "POC"
#     "Environment" = "prd"
#     "Owner" = "Samson"
#     }
# }
