# Create Workspace root S3 bucket (DBFS root)
resource "aws_s3_bucket" "web_app" {
  bucket = "${var.bucket_prefix}-${var.environment_name}"
}

# Recommended: block public access
resource "aws_s3_bucket_public_access_block" "root" {
  bucket                  = aws_s3_bucket.web_app.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# (Optional but recommended) Versioning & encryption
resource "aws_s3_bucket_versioning" "root_v" {
  bucket = aws_s3_bucket.web_app.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "root_sse" {
  bucket = aws_s3_bucket.web_app.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}