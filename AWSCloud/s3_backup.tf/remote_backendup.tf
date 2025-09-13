terraform {
    backend "s3" {
        bucket         =  "dbx-backend-tf-sbx"
        key            = "tfstate_sandbox/terraform.tfstate"
        region         = "us-east-1"
     
        #profile        = "my-aws-profile" # optional, if you use AWS named profiles
    }
   
}