#!/bin/bash

################################################################################
# Terraform State Management Setup for Azure
# This script creates the Azure Storage Account and Container for Terraform state
# Run this ONCE before first Terraform deployment
################################################################################

set -e

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SUBSCRIPTION_ID="${AZURE_SUBSCRIPTION_ID}"
RESOURCE_GROUP="${TERRAFORM_STATE_RG:-terraform-state}"
LOCATION="${TERRAFORM_STATE_LOCATION:-eastus}"
STORAGE_ACCOUNT="tfstate$(date +%s | tail -c 5)" # Random suffix for uniqueness
CONTAINER_NAME="tfstate"
STATE_FILE="terraform.tfstate"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Terraform State Management Setup${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Validation
if [ -z "$SUBSCRIPTION_ID" ]; then
    echo -e "${RED}Error: AZURE_SUBSCRIPTION_ID not set${NC}"
    exit 1
fi

echo -e "${YELLOW}Configuration:${NC}"
echo "  Subscription ID: $SUBSCRIPTION_ID"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  Location: $LOCATION"
echo "  Storage Account: $STORAGE_ACCOUNT"
echo "  Container: $CONTAINER_NAME"
echo ""

# Step 1: Set subscription
echo -e "${YELLOW}Step 1: Setting Azure subscription...${NC}"
az account set --subscription "$SUBSCRIPTION_ID"
echo -e "${GREEN}✓ Subscription set${NC}"
echo ""

# Step 2: Create resource group
echo -e "${YELLOW}Step 2: Creating resource group...${NC}"
az group create \
  --name "$RESOURCE_GROUP" \
  --location "$LOCATION" \
  --tags "Purpose=TerraformState" "ManagedBy=Terraform"
echo -e "${GREEN}✓ Resource group created${NC}"
echo ""

# Step 3: Create storage account
echo -e "${YELLOW}Step 3: Creating storage account...${NC}"
az storage account create \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT" \
  --location "$LOCATION" \
  --sku Standard_LRS \
  --kind StorageV2 \
  --https-only true \
  --min-tls-version TLS1_2 \
  --enable-hns false \
  --tags "Purpose=TerraformState" "ManagedBy=Terraform"
echo -e "${GREEN}✓ Storage account created: $STORAGE_ACCOUNT${NC}"
echo ""

# Step 4: Get storage account key
echo -e "${YELLOW}Step 4: Retrieving storage account key...${NC}"
STORAGE_KEY=$(az storage account keys list \
  --resource-group "$RESOURCE_GROUP" \
  --account-name "$STORAGE_ACCOUNT" \
  --query '[0].value' -o tsv)
echo -e "${GREEN}✓ Storage key retrieved${NC}"
echo ""

# Step 5: Create container
echo -e "${YELLOW}Step 5: Creating blob container...${NC}"
az storage container create \
  --name "$CONTAINER_NAME" \
  --account-name "$STORAGE_ACCOUNT" \
  --account-key "$STORAGE_KEY"
echo -e "${GREEN}✓ Container created: $CONTAINER_NAME${NC}"
echo ""

# Step 6: Enable versioning
echo -e "${YELLOW}Step 6: Enabling storage account versioning...${NC}"
az storage account blob-service-properties update \
  --account-name "$STORAGE_ACCOUNT" \
  --account-key "$STORAGE_KEY" \
  --enable-versioning true
echo -e "${GREEN}✓ Versioning enabled${NC}"
echo ""

# Step 7: Configure storage firewall
echo -e "${YELLOW}Step 7: Configuring storage account firewall...${NC}"
az storage account update \
  --resource-group "$RESOURCE_GROUP" \
  --name "$STORAGE_ACCOUNT" \
  --default-action Deny
echo -e "${GREEN}✓ Firewall configured (default: Deny)${NC}"
echo ""

# Step 8: Save configuration
echo -e "${YELLOW}Step 8: Saving configuration...${NC}"
cat > terraform/backend-config.hcl << EOF
# Auto-generated Terraform backend configuration
# This file should be committed to version control (no secrets)

resource_group_name  = "$RESOURCE_GROUP"
storage_account_name = "$STORAGE_ACCOUNT"
container_name       = "$CONTAINER_NAME"
key                  = "$STATE_FILE"
EOF

echo -e "${GREEN}✓ Backend config saved to: terraform/backend-config.hcl${NC}"
echo ""

# Step 9: Display next steps
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Next Steps:${NC}"
echo "1. Export storage account key (add to .env):"
echo -e "   ${GREEN}export ARM_ACCESS_KEY='$STORAGE_KEY'${NC}"
echo ""
echo "2. Initialize Terraform with backend:"
echo -e "   ${GREEN}cd terraform${NC}"
echo -e "   ${GREEN}terraform init -backend-config=backend-config.hcl${NC}"
echo ""
echo "3. Verify state is stored in Azure:"
echo -e "   ${GREEN}az storage blob list --container-name $CONTAINER_NAME --account-name $STORAGE_ACCOUNT --account-key \$ARM_ACCESS_KEY${NC}"
echo ""

# Step 10: Save to .env file (optional)
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}Creating .env file...${NC}"
    cat > .env << EOF
# Azure Terraform State Configuration
export ARM_SUBSCRIPTION_ID="$SUBSCRIPTION_ID"
export ARM_ACCESS_KEY="$STORAGE_KEY"
export TERRAFORM_STATE_RG="$RESOURCE_GROUP"
export TERRAFORM_STATE_STORAGE="$STORAGE_ACCOUNT"
export TERRAFORM_STATE_CONTAINER="$CONTAINER_NAME"
EOF
    echo -e "${GREEN}✓ .env file created (keep this secure!)${NC}"
    echo ""
fi

echo -e "${GREEN}✓ Setup completed successfully!${NC}"
echo ""
echo -e "${YELLOW}Important:${NC}"
echo "- Keep storage account key secure (in .env, not in Git)"
echo "- Store state file versioning enabled for rollback"
echo "- Use ARM_ACCESS_KEY environment variable for CI/CD"
echo "- Add .env to .gitignore"
echo ""
