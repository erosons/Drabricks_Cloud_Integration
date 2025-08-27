
# # Let the Databricks provider generate the correct trust policy for you
# data "databricks_aws_assume_role_policy" "uc_trust" {
#   external_id = var.databricks_account_id
# }

# resource "aws_iam_role" "metastore_data_access" {
#   name               = "uc-metastore-role"
#   assume_role_policy = data.databricks_aws_assume_role_policy.uc_trust.json
# }

# # Attach inline policy (your screenshot JSON) to the role
# # Inline permissions for the UC storage role (limit to your bucket/prefix)
# resource "aws_iam_role_policy" "metastore_data_access_policy" {
#   name = "uc-metastore-policy"
#   role = aws_iam_role.metastore_data_access.id

#   policy = jsonencode({
#     Version = "2012-10-17",
#     Statement = [
#       {
#         Effect = "Allow",
#         Action = [
#           "s3:GetObject",
#           "s3:PutObject",
#           "s3:DeleteObject"
#         ],
#         Resource = [
#           "${aws_s3_bucket.ms.bucket.arn}/metastore/*"
#         ]
#       },
#       {
#         Effect = "Allow",
#         Action = [
#           "s3:ListBucket",
#           "s3:GetBucketLocation"
#         ],
#         Resource = "${aws_s3_bucket.ms.bucket.arn}",
#         Condition = {
#           StringLike = {
#             "s3:prefix" : ["metastore/*"]
#           }
#         }
#       }
#     ]
#   })
# }
