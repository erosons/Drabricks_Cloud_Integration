# 1) EC2 instance role & instance profile
resource "aws_iam_role" "ec2_role" {
  name = "ec2-${var.environment_name}-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Principal = { Service = "ec2.amazonaws.com" },
      Action   = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_instance_profile" "ec2_profile" {
  name = "ec2-${var.environment_name}-profile"
  role = aws_iam_role.ec2_role.name
}

# 2) Allow read/write only to the desired bucket/prefix
resource "aws_iam_role_policy" "ec2_s3_access" {
  name = "ec2-s3-bucket-access"
  role = aws_iam_role.ec2_role.id
  policy = jsonencode({
    Version = "2012-10-17",
    Statement = [{
      Effect = "Allow",
      Action = [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket"
      ],
      Resource = [
         "${aws_s3_bucket.web_app.arn}",
        "${aws_s3_bucket.web_app.arn}/*"
      ]
    }]
  })
}
