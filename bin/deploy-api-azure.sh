#!/usr/bin/env bash

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${BLUE}=== Azure Container Apps Deployment Script ===${NC}\n"

# Configuration - Update these values or set as environment variables
RESOURCE_GROUP="${AZURE_RESOURCE_GROUP:-rg-sunbird-ai-prod}"
ACR_NAME="${AZURE_ACR_NAME:-sunbirdaiacrprod}"
CONTAINER_APP_NAME="${AZURE_CONTAINER_APP_NAME:-ca-sunbird-ai-api-prod}"
IMAGE_NAME="sunbird-ai-api"

# Generate image tag from git SHA
GIT_SHA=$(git rev-parse --short HEAD)
IMAGE_TAG="${ACR_NAME}.azurecr.io/${IMAGE_NAME}:${GIT_SHA}"

echo -e "${BLUE}Configuration:${NC}"
echo "  Resource Group: $RESOURCE_GROUP"
echo "  ACR Name: $ACR_NAME"
echo "  Container App: $CONTAINER_APP_NAME"
echo "  Image Tag: $IMAGE_TAG"
echo ""

# Step 1: Check Azure CLI authentication
echo -e "${BLUE}Step 1: Checking Azure CLI authentication...${NC}"
if ! az account show &> /dev/null; then
    echo -e "${RED}Error: Not logged in to Azure CLI${NC}"
    echo "Please run: az login"
    exit 1
fi

SUBSCRIPTION_NAME=$(az account show --query name -o tsv)
echo -e "${GREEN}✓ Logged in to Azure (Subscription: $SUBSCRIPTION_NAME)${NC}\n"

# Step 2: Build Docker image
echo -e "${BLUE}Step 2: Building Docker image...${NC}"
docker build -f Dockerfile.azure -t $IMAGE_TAG .
echo -e "${GREEN}✓ Docker image built successfully${NC}\n"

# Step 3: Login to Azure Container Registry
echo -e "${BLUE}Step 3: Logging in to Azure Container Registry...${NC}"
az acr login --name $ACR_NAME
echo -e "${GREEN}✓ Logged in to ACR${NC}\n"

# Step 4: Push image to ACR
echo -e "${BLUE}Step 4: Pushing image to Azure Container Registry...${NC}"
docker push $IMAGE_TAG
echo -e "${GREEN}✓ Image pushed successfully${NC}\n"

# Step 5: Update Container App
echo -e "${BLUE}Step 5: Updating Azure Container App...${NC}"
az containerapp update \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --image $IMAGE_TAG

echo -e "${GREEN}✓ Container App updated successfully${NC}\n"

# Step 6: Get deployment URL
echo -e "${BLUE}Step 6: Retrieving deployment URL...${NC}"
FQDN=$(az containerapp show \
  --name $CONTAINER_APP_NAME \
  --resource-group $RESOURCE_GROUP \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv)

echo -e "${GREEN}✓ Deployment completed successfully!${NC}\n"
echo -e "${BLUE}=== Deployment Summary ===${NC}"
echo "  Application URL: https://$FQDN"
echo "  Image: $IMAGE_TAG"
echo "  Git SHA: $GIT_SHA"
echo ""
echo -e "${GREEN}You can now test the application at: https://$FQDN${NC}"
