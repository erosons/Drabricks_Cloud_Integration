###############################################
# Create Workspace UC MetaStore S3 bucket
###############################################


resource "aws_s3_bucket" "uc_metastore" {
  bucket = "dbx-uc-metastore-${var.aws_region}-${random_string.suffix.result}"
    lifecycle {
    prevent_destroy = false
  }
  force_destroy   = true
}

# Recommended: block public access
resource "aws_s3_bucket_public_access_block" "uc" {
  bucket                  = aws_s3_bucket.uc_metastore.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# (Optional but recommended) Versioning & encryption
resource "aws_s3_bucket_versioning" "uc_metastore_v" {
  bucket = aws_s3_bucket.uc_metastore.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "uc_metastore_sse" {
  bucket = aws_s3_bucket.uc_metastore.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}


# # Bucket policy that lets the Databricks role access the root bucket
data "databricks_aws_bucket_policy" "this" {
  bucket   = aws_s3_bucket.uc_metastore.bucket
  provider = databricks.mws
}


# Bucket policy that lets the Databricks role access the root bucket
# databricks mapped bucket policy is mapped to aws s3 bucket policy
resource "aws_s3_bucket_policy" "root_bucket_policy" {
  bucket     = aws_s3_bucket.uc_metastore.id
  policy     = data.databricks_aws_bucket_policy.this.json
  depends_on = [aws_s3_bucket_public_access_block.uc]
}