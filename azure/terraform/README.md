# Azure Infrastructure - Terraform Configuration

This directory contains Terraform configuration for provisioning Azure infrastructure for the Sunbird AI API deployment to Azure Container Apps.

## Prerequisites

Before you begin, ensure you have:

1. **Azure CLI** installed and configured
   ```bash
   # Install Azure CLI (macOS)
   brew install azure-cli

   # Login to Azure
   az login

   # Set the subscription you want to use
   az account set --subscription "<subscription-id>"
   ```

2. **Terraform** installed (version >= 1.0)
   ```bash
   # Install Terraform (macOS)
   brew install terraform

   # Verify installation
   terraform version
   ```

3. **Azure Subscription** with appropriate permissions to create resources

## Resources Created

This Terraform configuration provisions the following Azure resources:

- **Resource Group** - Container for all Azure resources
- **Azure Container Registry (ACR)** - Docker image repository
- **Log Analytics Workspace** - Foundation for monitoring and logging
- **Application Insights** - Application performance monitoring
- **Container Apps Environment** - Managed infrastructure for Container Apps
- **Container App** - The Sunbird AI API application

## Getting Started

### Step 1: Configure Variables

Copy the example variables file and customize it:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your specific values:

```hcl
location     = "eastus"              # Azure region
environment  = "prod"                # Environment name
project_name = "sunbird-ai"          # Project identifier
acr_sku      = "Basic"               # ACR tier
```

### Step 2: Register Azure Resource Providers

**IMPORTANT**: Before running Terraform, register the required Azure resource providers:

```bash
# Register all required providers
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.Insights

# Verify registration (wait until all show "Registered")
az provider list --query "[?namespace=='Microsoft.App' || namespace=='Microsoft.OperationalInsights' || namespace=='Microsoft.ContainerRegistry' || namespace=='Microsoft.Insights'].{Namespace:namespace, State:registrationState}" -o table
```

**Note**: Registration takes 2-5 minutes. This is a one-time setup per Azure subscription.

### Step 3: Initialize Terraform

Initialize the Terraform working directory:

```bash
terraform init
```

This will:
- Download the Azure provider plugin
- Initialize the backend
- Prepare the working directory

### Step 4: Review the Plan

Generate and review the execution plan:

```bash
terraform plan
```

Review the output carefully to ensure the correct resources will be created.

### Step 5: Apply the Configuration

Create the infrastructure:

```bash
terraform apply
```

Type `yes` when prompted to confirm.

This process typically takes 3-5 minutes to complete.

### Step 6: Save the Outputs

After successful deployment, save the important outputs:

```bash
# View all outputs
terraform output

# Save specific outputs for GitHub Secrets
terraform output -raw resource_group_name
terraform output -raw acr_name
terraform output -raw container_app_name
terraform output -raw application_insights_connection_string
```

## Important Outputs

The following outputs are needed for configuring GitHub Actions:

| Output | Description | Used In |
|--------|-------------|---------|
| `resource_group_name` | Resource group name | GitHub Secrets: `AZURE_RESOURCE_GROUP` |
| `acr_name` | Container registry name | GitHub Secrets: `AZURE_ACR_NAME` |
| `acr_login_server` | ACR login server URL | Docker image tagging |
| `container_app_name` | Container App name | GitHub Secrets: `AZURE_CONTAINER_APP_NAME` |
| `container_app_url` | Application URL | Testing and verification |
| `application_insights_connection_string` | App Insights connection | GitHub Secrets: `APPLICATIONINSIGHTS_CONNECTION_STRING` |

## Configuring GitHub Secrets

After provisioning infrastructure, configure these GitHub Secrets:

### 1. Create Azure Service Principal

```bash
# Create a service principal with Contributor role
az ad sp create-for-rbac \
  --name "sunbird-ai-github-actions" \
  --role Contributor \
  --scopes /subscriptions/<subscription-id>/resourceGroups/$(terraform output -raw resource_group_name) \
  --sdk-auth
```

Save the JSON output as GitHub Secret: `AZURE_CREDENTIALS`

### 2. Add Terraform Outputs to GitHub Secrets

```bash
# In your GitHub repository settings, add these secrets:
AZURE_RESOURCE_GROUP=$(terraform output -raw resource_group_name)
AZURE_ACR_NAME=$(terraform output -raw acr_name)
AZURE_CONTAINER_APP_NAME=$(terraform output -raw container_app_name)
APPLICATIONINSIGHTS_CONNECTION_STRING=$(terraform output -raw application_insights_connection_string)
```

## Updating Infrastructure

To update the infrastructure:

```bash
# Modify variables in terraform.tfvars or *.tf files
# Review changes
terraform plan

# Apply changes
terraform apply
```

## Destroying Infrastructure

To remove all resources (use with caution):

```bash
terraform destroy
```

Type `yes` when prompted to confirm deletion.

## State Management

### Local State (Current Setup)

The Terraform state is currently stored locally in `terraform.tfstate`.

**Important**:
- Do NOT commit `terraform.tfstate` to version control
- The state file is already in `.gitignore`
- Consider migrating to remote state for production

### Migrating to Remote State (Recommended for Production)

For production deployments, use Azure Storage for remote state:

```hcl
# Add to provider.tf
terraform {
  backend "azurerm" {
    resource_group_name  = "rg-terraform-state"
    storage_account_name = "tfstatesunbirdai"
    container_name       = "tfstate"
    key                  = "sunbird-ai-api.tfstate"
  }
}
```

## Troubleshooting

### Error: Resource Provider Not Registered

```
Error: creating Managed Environment: MissingSubscriptionRegistration:
The subscription is not registered to use namespace 'Microsoft.App'
```

**Solution**: Register the required Azure resource providers before running Terraform:

```bash
# Register all required providers
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
az provider register --namespace Microsoft.ContainerRegistry
az provider register --namespace Microsoft.Insights

# Wait for registration to complete (2-5 minutes)
az provider show --namespace Microsoft.App --query "registrationState" -o tsv

# Once it shows "Registered", run terraform apply again
```

This is a **one-time setup** per Azure subscription. See [Step 2](#step-2-register-azure-resource-providers) for more details.

### Error: Insufficient Permissions

```
Error: authorization failed
```

**Solution**: Ensure your Azure account has sufficient permissions. You may need `Contributor` or `Owner` role.

### Error: Name Already Exists

```
Error: The name 'acrsunbirdaiprod' is already taken
```

**Solution**: ACR names must be globally unique. Change the `project_name` variable or modify the ACR name in `main.tf`.

### Error: Quota Exceeded

```
Error: quota exceeded for resource type
```

**Solution**: Check your subscription quotas and request increases if needed:

```bash
az vm list-usage --location eastus --output table
```

## Cost Estimation

Estimated monthly costs (as of 2024):

| Resource | SKU/Tier | Estimated Cost |
|----------|----------|----------------|
| Container App | 0.5 vCPU, 1.0 Gi RAM | $10-50/month |
| ACR | Basic | $5/month |
| Log Analytics | Pay-per-GB | $2-10/month |
| Application Insights | Included with Log Analytics | Included |

**Total**: ~$17-65/month depending on usage

Enable cost alerts in Azure Portal to monitor spending.

## Best Practices

1. **Resource Naming**: Follow Azure naming conventions and include environment in names
2. **Tags**: Use consistent tagging for resource management and cost tracking
3. **State Management**: Use remote state for team collaboration
4. **Variables**: Use `terraform.tfvars` for environment-specific values
5. **Secrets**: Never commit sensitive values; use Azure Key Vault for production
6. **Version Control**: Commit all `.tf` files except `terraform.tfvars` and `*.tfstate`

## Additional Resources

- [Azure Container Apps Documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure CLI Reference](https://learn.microsoft.com/en-us/cli/azure/)

## Support

For issues or questions:
1. Check the [Troubleshooting](#troubleshooting) section
2. Review Terraform and Azure documentation
3. Contact the DevOps team
