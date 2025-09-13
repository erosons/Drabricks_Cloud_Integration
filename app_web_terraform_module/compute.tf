resource "aws_instance" "instance_1" {
  ami           = var.ami # Amazon Linux 2 AMI (HVM), SSD Volume Type
  instance_type = var.instance_type
  vpc_security_group_ids = [aws_security_group.default.id] # Replace with your security group ID
  ebs_block_device {
    device_name = "/dev/xvda"
    volume_size = 8
    volume_type = "gp2"
    delete_on_termination = true
  }
  
  subnet_id = local.chosen_subnet_id    # Replace with your subnet ID
  associate_public_ip_address = true 
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name # Replace with your IAM role name
  user_data = <<-EOF
              #!/bin/bash
              echo "Hello, World1" > index.html
              nohup python3 -m http.server 8080 &
              EOF
  tags = var.tags
}

resource "aws_instance" "instance_2" {
  ami           = var.ami # Amazon Linux 2 AMI (HVM), SSD Volume Type
  instance_type = var.instance_type
  vpc_security_group_ids = [aws_security_group.default.id] # Replace with your security group ID
  ebs_block_device {
    device_name = "/dev/xvda"
    volume_size = 8
    volume_type = "gp2"
    delete_on_termination = true
  }
  
  subnet_id = local.chosen_subnet_id   # Replace with your subnet ID
  associate_public_ip_address = true 
  iam_instance_profile = aws_iam_instance_profile.ec2_profile.name # Replace with your IAM role name
  user_data = <<-EOF
              #!/bin/bash
              echo "Hello, World2" > index.html
              nohup python3 -m http.server 8080 &
              EOF
  tags = var.tags
}