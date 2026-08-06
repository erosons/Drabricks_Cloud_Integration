#!/bin/bash

# Authenticate with Azure
az login
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"

# Set environment variable for MSI authentication if using MSI
export ARM_USE_MSI=true

# Navigate to the test directory
cd path/to/your/test/folder

# Initialize Terraform
terraform init

# Plan (there are 2 options) and apply 
terraform plan -var-file="cluster.auto.tfvars" -var-file="job.auto.tfvars" -var-file="notebook.tfvars" -out=tfplan | terraform plan -out=tfplan (keep all var in -> terraform.tfvars)
terraform apply "tfplan" | terraform apply -auto-approve
terraform apply "tfplan" -destroy -auto-approve

# CREATE AND SPN ROLE Assign the Contributor Role on the Databricks Workspace:
az role assignment create --assignee "<SPN_CLIENT_ID>" \
  --role "Contributor" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.Databricks/workspaces/<WORKSPACE_NAME>"
  
# Assign Storage Blob Data Contributor Role on Storage Accounts (if needed):
  az role assignment create --assignee "<SPN_CLIENT_ID>" \
  --role "Storage Blob Data Contributor" \
  --scope "/subscriptions/<SUBSCRIPTION_ID>/resourceGroups/<RESOURCE_GROUP>/providers/Microsoft.Storage/storageAccounts/<STORAGE_ACCOUNT_NAME>"




# ################################################
# Terraform Plan Error and Why for Resource Deployment
# ##################################################

When deploying resources in Azure with Terraform, certain resource providers (e.g., Microsoft.KeyVault, Microsoft.AppConfiguration, etc.) must be registered to allow the creation of resources associated with them. By default, Terraform tries to automatically register this services.

# Option 1: Grant the Service Principal (SPN) Higher 

If possible, assign the "Contributor"/"Owner" role to the SPN at the subscription level. This should give it the necessary permissions to register resource providers.

# Option2 manually | Run the bash script
az login
az account set --subscription "<YOUR_SUBSCRIPTION_ID>"

# Register individual providers as needed
az provider register --namespace Microsoft.KeyVault
az provider register --namespace Microsoft.AppConfiguration
az provider register --namespace Microsoft.BotService
az provider register --namespace Microsoft.SecurityInsights
# Continue this pattern for other providers listed in your error message.

# Option 3: Disable Automatic Resource Provider Registration

If you want to avoid automatic provider registration altogether (though not recommended if new providers are required), you can add resource_provider_registrations = "none" to the azurerm provider block. This means Terraform will not try to register providers, but if a provider is not registered, resource creation for that provider will fail.