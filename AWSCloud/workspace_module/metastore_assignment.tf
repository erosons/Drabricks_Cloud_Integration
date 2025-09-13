################################################################################
# Unity Catalog: Metastore + Data Access + Assignment
################################################################################

# Discover all metastores (account-level)
data "databricks_metastores" "all" {

    provider = databricks.mws
}


# make a guaranteed-non-null map
locals {
  all_metastore_ids = data.databricks_metastores.all.ids != null ? data.databricks_metastores.all.ids : tomap({})
}

data "databricks_metastore" "detail" {
  provider     = databricks.mws
  for_each     = local.all_metastore_ids   # map(name -> id); never null
  metastore_id = each.value
}



# 3) Pick the one in our target region; create only if none exists
locals {
  # Depending on provider version, region may be top-level or inside metastore_info
  metastores_in_region = [
    for name, d in data.databricks_metastore.detail :
    d.id
    if try(d.region, try(d.metastore_info[0].region, null)) == var.aws_region
  ]

  discovered_metastore_id = try(one(local.metastores_in_region), null)

  create_uc_metastore = var.unity_catalog_metastore && local.discovered_metastore_id == null
}


resource "databricks_metastore" "new" {
  provider     = databricks.mws
  count = local.create_uc_metastore ? 1 : 0
  name          = var.metastore_name
  # storage_root  = "s3://${aws_s3_bucket.uc_metastore.bucket}/metastore"
  region        = var.aws_region
  force_destroy = true
}


# 4) Effective metastore id: prefer created, else discovered
locals {
  metastore_id = local.create_uc_metastore ? databricks_metastore.new[0].id: local.discovered_metastore_id
}

# fail fast if we still don't have an id
resource "null_resource" "ensure_metastore" {
  triggers = { metastore_id = local.metastore_id != null ? local.metastore_id : "MISSING" }
  lifecycle {
    precondition {
      condition     = local.metastore_id != null
      error_message = "No metastore found/created in ${var.aws_region}."
    }
  }
}


resource "databricks_metastore_data_access" "this" {
  provider     = databricks.mws
  metastore_id = local.metastore_id
  name         = "assignment-${local.prefix}"
  aws_iam_role { role_arn = databricks_mws_credentials.this.role_arn }
  is_default   = true
  depends_on   = [
                   null_resource.ensure_metastore,
                   databricks_mws_storage_configurations.this
                   ]
   # Provider sometimes flips is_default/read_only on read
  lifecycle { 
     ignore_changes = [is_default, read_only] 
     }
}

resource "databricks_metastore_assignment" "this" {
  provider     = databricks.mws
  metastore_id = local.metastore_id
  workspace_id = databricks_mws_workspaces.this.workspace_id

  depends_on   = [
        time_sleep.wait_for_workspace,
        databricks_metastore_data_access.this,
        null_resource.ensure_metastore
    ]
}

