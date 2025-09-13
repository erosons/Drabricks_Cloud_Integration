terraform {
    backend "s3" {
        bucket         =  "dbx-backend-tf-sbx"
        key            = "tfstate_sandbox/web_app_demo/terraform.tfstate"
        region         = "us-east-1"
        dynamodb_table = "dbx-remote-state-lock"
        encrypt        = true
        #profile        = "my-aws-profile" # optional, if you use AWS named profiles
    }

required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
  
}