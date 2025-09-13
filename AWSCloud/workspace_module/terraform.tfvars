
aws_region                    = "us-east-1"
workspace_name_prefix         = "dbx-databricks-wk-sbx"
access_connector_prefix       = "dbx-access-connector-sbx"
bucket_name_prefix            = "dbx-bucket-sbx"
tf_backend_bucket             = "dbx-backend-tf-sbx"
dynamodb_table_name           = "dbx-remote-state-lock"
databricks_account_id         = "67690736-ed9f-4566-9c09-6ce4af6eb2e3"
vpc_id                        = "vpc-0f80ef0a48b036fe8"
network_prefix                = "dbx-network-sbx"
subnets_private_ids           = ["subnet-0f0beef3de5e7fa66","subnet-058abd6ad47cdfe3c"]
security_group_ids            = "sg-0c04dbd290b14cf7c"
client_id                     = "1555a90d-4e32-4e0a-8de0-ea21737e6e5e"
client_secret                 = "dose105f40c78180b9573a2150aff2ff2f4f"

//aad_groups              = ["account_unity_admin", "data_engineer", "data_analyst", "data_scientist"]
tags = {
  "Project" = "POC"
  "Environment" = "Sandbox"
  "Owner" = "Samson"
}



