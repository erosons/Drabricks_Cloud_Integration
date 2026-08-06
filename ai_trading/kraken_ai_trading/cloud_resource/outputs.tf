output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.kraken_bot.id
}

output "public_ip" {
  description = "Elastic IP — stable across restarts"
  value       = aws_eip.kraken_bot.public_ip
}

output "private_ip" {
  description = "Private IP within the VPC"
  value       = aws_instance.kraken_bot.private_ip
}

output "instance_type" {
  description = "Instance type deployed"
  value       = aws_instance.kraken_bot.instance_type
}

output "ami_id" {
  description = "Amazon Linux 2023 AMI used"
  value       = data.aws_ami.al2023.id
}

output "ssh_command" {
  description = "SSH command to connect to the instance"
  value       = "ssh -i ~/.ssh/${var.key_pair_name}.pem ec2-user@${aws_eip.kraken_bot.public_ip}"
}

output "deploy_command" {
  description = "Run this from the kraken_ai_trading directory to push code"
  value       = "bash cloud_resource/deploy.sh ${aws_eip.kraken_bot.public_ip} ~/.ssh/${var.key_pair_name}.pem"
}

output "grafana_url" {
  description = "Grafana monitoring dashboard"
  value       = "http://${aws_eip.kraken_bot.public_ip}:3000"
}

output "prometheus_url" {
  description = "Prometheus metrics endpoint"
  value       = "http://${aws_eip.kraken_bot.public_ip}:9090"
}
