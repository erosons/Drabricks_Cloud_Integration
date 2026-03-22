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
  storage_root  = "s3://${aws_s3_bucket.uc_metastore.bucket}/metastore"
  region        = var.aws_region
  force_destroy = true
}



