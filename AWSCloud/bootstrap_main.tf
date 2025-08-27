
#--------------------------------------------------------------------------------
# --- Bootstrap Starting s3 bucket and DynamoDB for tf backend -----------------
#------------------------------------------------------------------------------
resource "aws_s3_bucket" "tf_backend" {
  bucket = var.tf_backend_bucket
  force_destroy = true
}

# Recommended: block public access
resource "aws_s3_bucket_public_access_block" "tf_backend" {
  bucket                  = aws_s3_bucket.tf_backend.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_versioning" "example" {
  bucket = aws_s3_bucket.tf_backend.id
  versioning_configuration {
    status = "Enabled"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "example" {
  bucket = aws_s3_bucket.tf_backend.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "AES256"
    }
  }
}

resource "aws_dynamodb_table" "tf_lock" {
  name         = var.dynamodb_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
#-------------Boortstrap ends here this used to to map s3 backend by adding this backend  in Remote_backend.tf-----------------


