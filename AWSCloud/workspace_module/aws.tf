
# Configure Cross -account IAM role using Databricks-genrated STS assume role policy
resource "aws_iam_role" "cross_account_role" {
  name               = "${local.prefix}-crossaccount"
  assume_role_policy = data.databricks_aws_assume_role_policy.this.json
  tags               = var.tags
  max_session_duration = 3600
}


# Policy for the cross-account IAM  role (uses Databricks-managed/generated policy)
# Attach Databricks-managed policy with required permissions
resource "aws_iam_role_policy" "this" {
  name   = "${local.prefix}-policy"
  role   = aws_iam_role.cross_account_role.id
  policy = data.databricks_aws_crossaccount_policy.this.json
}

# Insert artifificial delay to avoid eventual consistency issues with IAM role creation and usage
resource "time_sleep" "wait_30_seconds" {
  depends_on = [aws_iam_role.cross_account_role, aws_iam_role_policy.this]
  create_duration = "30s"
}

# ------------------------------------------------------------------------------------
# Provisioning Workspace and Root S3 bucket which will be mapped  storage configuration
# -------------------------------------------------------------------------------------

# Create Workspace root S3 bucket (DBFS root)
resource "aws_s3_bucket" "root" {
  bucket = "dbx-root-${var.aws_region}-${random_string.suffix.result}"
  lifecycle {
    prevent_destroy = false
  }
  force_destroy   = true
}

# Recommended: block public access
resource "aws_s3_bucket_public_access_block" "root" {
  bucket                  = aws_s3_bucket.root.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# (Optional but recommended) Versioning & encryption
resource "aws_s3_bucket_versioning" "root_v" {
  bucket = aws_s3_bucket.root.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "root_sse" {
  bucket = aws_s3_bucket.root.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}


# Bucket policy that lets the Databricks role access the root bucket
# databricks mapped bucket policy is mapped to aws s3 bucket policy
resource "aws_s3_bucket_policy" "root_bucket_policy" {
  bucket     = aws_s3_bucket.root.id
  policy     = data.databricks_aws_bucket_policy.this.json
  depends_on = [aws_s3_bucket_public_access_block.root]
}

