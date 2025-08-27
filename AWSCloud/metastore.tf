# # Create Workspace root S3 bucket (DBFS root)
# resource "aws_s3_bucket" "ms" {
#   bucket = "dbx-metastore-${var.aws_region}-${random_string.suffix.result}"
# }

# # Recommended: block public access
# resource "aws_s3_bucket_public_access_block" "rootms" {
#   bucket                  = aws_s3_bucket.ms.id
#   block_public_acls       = true
#   block_public_policy     = true
#   ignore_public_acls      = true
#   restrict_public_buckets = true
# }

# # (Optional but recommended) Versioning & encryption
# resource "aws_s3_bucket_versioning" "root_m" {
#   bucket = aws_s3_bucket.ms.id
#   versioning_configuration {
#     status = "Enabled"
#   }
# }

# resource "aws_s3_bucket_server_side_encryption_configuration" "root_ssem" {
#   bucket = aws_s3_bucket.ms.id
#   rule {
#     apply_server_side_encryption_by_default {
#       sse_algorithm = "AES256"
#     }
#   }
# }


# # ################################################################################
# # # Bucket policy (grant the role access) – build explicitly for clarity
# # ################################################################################
# # data "aws_iam_policy_document" "ms_bucket_policy" {
# #   statement {
# #     sid     = "UCDataAccessObjects"
# #     effect  = "Allow"
# #     actions = ["s3:GetObject","s3:PutObject","s3:DeleteObject"]
# #     resources = [
# #       "arn:aws:s3:::${aws_s3_bucket.ms.bucket}/metastore/*"
# #     ]
# #     principals {
# #       type        = "AWS"
# #       identifiers = [aws_iam_role.metastore_data_access.arn]
# #     }
# #   }

# #   statement {
# #     sid     = "UCDataAccessList"
# #     effect  = "Allow"
# #     actions = ["s3:ListBucket","s3:GetBucketLocation"]
# #     resources = ["arn:aws:s3:::${aws_s3_bucket.ms.bucket}"]
# #     principals {
# #       type        = "AWS"
# #       identifiers = [aws_iam_role.metastore_data_access.arn]
# #     }
# #     condition {
# #       test     = "StringLike"
# #       variable = "s3:prefix"
# #       values   = ["metastore/*"]
# #     }
# #   }
# # }



# ################################################################################
# # Unity Catalog: Metastore + Data Access + Assignment
# ################################################################################
# resource "databricks_metastore" "this" {
#   name          = "uc-metastore"
#   storage_root  = "s3://${aws_s3_bucket.ms.bucket}/metastore"
#   region        = var.aws_region
#   force_destroy = false
#   owner         = "uc admins"
# }

# resource "databricks_metastore_data_access" "this" {
#   metastore_id = databricks_metastore.this.id
#   name         = "default-uc-storage-credential"
#   aws_iam_role {
#     role_arn = aws_iam_role.metastore_data_access.arn
#   }
#   is_default = true
# }

# # Example: assign the metastore to a workspace
# resource "databricks_metastore_assignment" "this" {
#   metastore_id = databricks_metastore.this.id
#   workspace_id = databricks_mws_workspaces.this.workspace_id
# }