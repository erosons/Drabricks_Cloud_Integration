##### Dependency Graph - Meta Argument
# https://developer.hashicorp.com/terraform/language

//Terraform uses depends_on to to drive the order of follow to enforce dependence

resource "aws_instance" "name" {
    count =4
    ami = var.image_id
    instance_type = var.instance_type
    depends_on = [ aws_iam_role.ec2_role ]
}


//Working Example of creating multiple nearly identical resources using 'count' meta-argument

resource "aws_iam_instance" "this"{
    count =4
    ami = var.image_id
    instance_type = var.instance_type

    tags ={
        Name ="Server-${count.index +1}"
    }
}


// Working Example of using 'for_each' meta-argument to create resources from a map

locals {
    server_map = {
        server1 = {
        ami           = var.image_id
        instance_type = "t3.micro"
        }
        server2 = {
        ami           = var.image_id
        instance_type = "t3.small"
        }
        server3 = {
        ami           = var.image_id
        instance_type = "t3.medium"
        }
    }

    subnet_ids= toset([
        "subnet-0123456789abcdef0",
        "subnet-0fedcba9876543210"
    ])
}

// Working  Create multiple EC2 instances using for_each
resource "aws_instance" "this" {
    for_each = local.server_map

    ami           = each.value.ami
    instance_type = each.value.instance_type

    tags = {
        Name = each.key
    }
}

// Create multiple subnets using for_each
resource "aws_instance" "subnet_instances" {
    for_each = local.subnet_ids
    ami           = var.image_id
    instance_type = var.instance_type
    subnet_id     = each.value
    }

###########################################################################
// Lifecycle Meta Argument : Additional controls over resource creation, update, and deletion
###########################################################################

- Prevent Destroy : /* To prevent a resource from being destroyed, 
you can use the prevent_destroy lifecycle argument. This is useful 
for critical resources that should not be accidentally deleted.*/
- Ignore Changes : /* If you want to ignore changes to specific attributes of a resource,
you can use the ignore_changes argument. This is useful when certain attributes
are managed outside of Terraform and you don't want Terraform to attempt to change them. */
- Create Before Destroy : /* To ensure that a new resource is created before the old one is destroyed,
you can use the create_before_destroy argument. This is useful for resources that require
high availability during updates. */


resource "aws_instance" "example" {
  ami           = var.image_id
  instance_type = var.instance_type

  lifecycle {
    prevent_destroy = true

    ignore_changes = [
      tags["Name"],
    ]
    create_before_destroy = true
  }
}

###########################################################################
# Provisioners  : Execute scripts on a local or remote machine as part of 
#resource creation or destruction.
###########################################################################
- Local-exec : /* The local-exec provisioner runs a command on the machine where Terraform is being executed.
This is useful for tasks like running local scripts or commands that interact with the local environment. */
- Remote-exec : /* The remote-exec provisioner runs commands on a remote machine after it has been created.
This is useful for configuring the machine, installing software, or running setup scripts. 
examples 
- Ansible playbook to configure the instance
- Shell script to install software packages
- PowerShell script to configure Windows instances
*/
- File provisioner : /* The file provisioner is used to copy files or directories from the local machine to a remote machine.
This is useful for transferring configuration files, scripts, or any other necessary files to the remote instance
*/
- Vendors
    - Chef :/* Chef is a configuration management tool that automates the process of managing and configuring infrastructure.
It uses a declarative language to define the desired state of the system and ensures that the system
is configured accordingly. */
    - Puppet /"* Puppet is another configuration management tool that automates the provisioning,
configuration, and management of infrastructure. It uses a declarative language to define the desired state
of the system and applies the necessary changes to achieve that state. */"
    - Salt /* Salt is an open-source configuration management and orchestration tool that allows you to manage
infrastructure at scale. It uses a master-minion architecture to execute commands and manage configurations
across multiple systems. */
    - Ansible /* Ansible is an open-source automation tool that simplifies the process of configuration management,
application deployment, and task automation. It uses a simple YAML-based language to define automation tasks
and can manage both local and remote systems. */

