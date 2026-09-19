

module "web_app_1" {
  source = "../app_web_terraform_module"

  # Input Variables
  bucket_prefix    = "webappdata01010-analytics"
  domain           = "careergene.com"
  app_name         = "web-app-1"
  environment_name = "dev"
  instance_type    = "t2.micro"
  create_dns_zone  = true
  # db_name          = "webapp1db"
  # db_user          = "foo"
  # db_pass          = var.db_pass_1
}

module "web_app_2" {
  source = "../app_web_module"

  # Input Variables
  bucket_prefix    = "webappdata01010-analytics"
  domain           = "careergene.com"
  app_name         = "web-app-2"
  environment_name = "production"
  instance_type    = "t2.micro"
  create_dns_zone  = true
  # db_name          = "webapp2db"
#   db_user          = "bar"
#   db_pass          = var.db_pass_2  Pass at runtime
}