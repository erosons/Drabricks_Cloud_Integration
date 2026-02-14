output "runner_instance_ids" {
  description = "IDs of the runner EC2 instances"
  value       = aws_instance.github_runner[*].id
}

output "runner_public_ips" {
  description = "Public IP addresses of runners"
  value       = aws_instance.github_runner[*].public_ip
}

output "runner_private_ips" {
  description = "Private IP addresses of runners"
  value       = aws_instance.github_runner[*].private_ip
}

output "security_group_id" {
  description = "Security group ID for runners"
  value       = aws_security_group.runner_sg.id
}

output "ssh_command" {
  description = "SSH commands to connect to runners"
  value = [
    for instance in aws_instance.github_runner :
    "ssh -i ~/.ssh/github-runner-key ubuntu@${instance.public_ip}"
  ]
}