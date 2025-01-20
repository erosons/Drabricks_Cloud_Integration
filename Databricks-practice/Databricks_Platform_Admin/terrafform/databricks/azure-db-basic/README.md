# main.tf: 
Contains the main resource configurations, including the resource group, Databricks workspace, storage account, container, and role assignment.

# variables.tf: 
Defines input variables for resources, making the script flexible and reusable across environments.

# locals.tf: 
Provides local expressions:

    Concatenates the storage account name with a random suffix (can be generated using random_string resource).
    Uses regex to sanitize the resource group name, ensuring it matches Azure naming conventions.

# data.tf: 
  Includes data sources to reference pre-existing resources or the current subscription. This allows checking for an existing resource group before creating a new one.

output.tf: Defines output values for resources created, such as the resource group name, Databricks workspace URL, storage account name, and container ID. These can be referenced in other modules or configurations.






# To run variable script
terraform apply -var-file="dev.tfvars"