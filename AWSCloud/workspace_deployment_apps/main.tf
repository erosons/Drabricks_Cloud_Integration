locals {
  environments = ["dev", "test", "uat"]
}

module "network" {
  source                 = "./modules/network"
  # workspace vpc
  vpc_cidr               = "10.10.0.0/16"
  ws_private_subnet_cidr = "10.10.1.0/24"
  ws_pe_subnet_cidr      = "10.10.3.0/27"

  # transit vpc for front-end
  transit_vpc_cidr       = "10.20.0.0/16"
  transit_pe_subnet_cidr = "10.20.1.0/27"

  name_prefix            = "dbx"
  tags                   = { env = "dev" }
}

module "dns" {
  source              = "./modules/dns"
  # Route53 private hosted zone just for Databricks PrivateLink mappings
  hosted_zone_name    = "privatelink.cloud.databricks.com"
  vpc_ids             = [module.network.transit_vpc_id] # PHZ needs to be visible from the transit VPC
}

module "private_endpoints" {
  source = "./modules/private_endpoints"

  # Back-end in workspace VPC
  workspace_vpc_id        = module.network.vpc_id
  backend_subnet_id       = module.network.ws_pe_subnet_id
  backend_sg_id           = module.network.backend_sg_id
  # Front-end in transit VPC
  transit_vpc_id          = module.network.transit_vpc_id
  frontend_subnet_id      = module.network.transit_pe_subnet_id
  frontend_sg_id          = module.network.frontend_sg_id

  # Regional Databricks endpoint service names (inputs)
  svc_name_workspace      = var.svc_name_workspace       # e.g., "com.amazonaws.vpce.us-east-1.vpce-svc-xxxxxxxx (Workspace)"
  svc_name_scc_relay      = var.svc_name_scc_relay       # e.g., "com.amazonaws.vpce.us-east-1.vpce-svc-yyyyyyyy (SCC relay)"

  name_prefix             = "dbx"
  tags                    = { env = "dev" }
}

module "workspace" {
  source = "./modules/databricks_workspace"

  # Databricks account-level (E2) wiring
  account_id                  = var.databricks_account_id
  aws_region                  = var.aws_region

  # Register VPCEs with Databricks, build PAS, & create workspace
  vpce_id_frontend            = module.private_endpoints.frontend_vpce_id
  vpce_id_backend_workspace   = module.private_endpoints.backend_workspace_vpce_id
  vpce_id_backend_scc         = module.private_endpoints.backend_scc_vpce_id

  # Customer-managed VPC (classic compute) details
  workspace_vpc_id            = module.network.vpc_id
  workspace_subnet_ids        = [module.network.ws_private_subnet_id]  # (add more AZs as needed)
  workspace_security_group_id = module.network.workspace_sg_id

  # Private Access Settings behavior
  private_access_public_enabled = false  # enforce PrivateLink only
  private_access_level          = "ENDPOINT"  # restrict to explicit VPCEs

  workspace_name              = "adb-ws-dev"
  name_prefix                 = "dbx"
  tags                        = { env = "dev" }
}

# Make the A & CNAME records that Databricks requires for front-end PL
module "dns_records" {
  source              = "./modules/dns/records"
  zone_id             = module.dns.zone_id
  workspace_hostname  = module.workspace.workspace_hostname  # <deployment>.cloud.databricks.com
  workspace_id        = module.workspace.workspace_id        # dbc-dp-<workspace-id>
  frontend_vpce_ip    = module.private_endpoints.frontend_vpce_ip
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
  security_group_ids            = ["sg-0c04dbd290b14cf7c"]
  name                          = "dbx-workspace-${each.key}"
    client_id                     = var.client_id
    client_secret                 = var.client_secret
    //aad_groups              = ["account_unity_admin", "data_engineer", "data_analyst", "data_scientist"]
    tags = {
    "Project" = "POC"
    "Environment" = each.key
    "Owner" = "Samson"
    }


}
