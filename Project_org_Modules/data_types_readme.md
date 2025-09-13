###### TYPES & VALIDATIONS #######

##### Primitive Types

- String
- Boolean
- number

##### Complex Types
- list()
- set()
- map()
- object({attr_name=type})
- tuples([types])

##### Validations
- Types Checking happens automatically
- Custom conditions can also be enforced


##### Retrieve variable from secretmanager
- Mark Variables as sensitive

data "environment_sensitive_variable" "path" {
  name = "PATH"
}

output "path" {
  value     = data.environment_sensitive_variable.path.value
  sensitive = true
}

##### When you .tfvars file other than terraform.tfvars
at runtime when apply you have to include  -var-file=other.tfvars

#### Passing passwords at runtime in CLI or GitActions
at runtime  -> -var=db_user=<username> -var="db_passord"

##### Dependency Graph - Meta Argument

Terraform uses depends_on to to drive the order of follow to enforce dependence