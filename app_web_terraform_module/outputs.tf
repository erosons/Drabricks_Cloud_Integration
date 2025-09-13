output "bucket_id" {
  value = aws_s3_bucket.web_app.id
}

output "subnet_ids" {
  value = data.aws_subnets.default.ids
}


output "instance_1_ip_addr" {
  value = aws_instance.instance_1.public_ip
}

output "instance_2_ip_addr" {
  value = aws_instance.instance_2.public_ip
}