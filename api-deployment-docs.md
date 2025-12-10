# Deployment Guide for the Sunbird AI Interference and API
There are 2 major components of the API deployment:
- The "inference server" which connects the models to hardware resources. (Currently deployed to Runpod-Read more about Runpod below)
    - [new-inference-server repo](https://github.com/SunbirdAI/sunbirdai-model-inferences)
- The user-facing API. (currently deployed on Cloud Run)
    - [sunbird-ai-api repo](https://github.com/SunbirdAI/sunbird-ai-api)

## Part A: Interference Deployment with Runpod
-Runpod is a cloud computing platform designed for Machine Learning and AI Applications and general compute.
-Execute your code utilising  both GPU and CPU resources through [Pods](https://docs.runpod.io/pods/overview) and
[Serverless](https://docs.runpod.io/serverless/overview) options
-You will need to create an account and get invited by a team member to use RunPod. Sign up for an account at [Runpod.io](https://www.runpod.io/) and for advanced account and permissions management you can use this link [here](https://docs.runpod.io/get-started/manage-accounts)

## What is RunPod Serverless?
- Runpod Serverless offers pay-per-second serverless GPU computing, bringing autoscaling to your production environment.The Serverless offering allows users to define a Worker, create a REST API Endpoint for it which queue jobs and autoscales to fill demand. This service, part of the Secure Cloud offering, guarantees low-cold start times and stringent security measures.

## How does RunPod Work?
- We can interact with Runpod through the following ways
-API
-CLI
-SDKs

## How to use CLI using the runpodctl
-runpodctl is an open source [open source command-line-interface(CLI)](https://github.com/runpod/runpodctl). You can use runpodctl to work with pods and RunPod Projects.

-Follow this [link](https://docs.runpod.io/cli/install-runpodctl) to be able to install and configure runpod CLI tool.

## How to interact with Runpod Serverless

RunPod generates an Endpoint ID that allows you to interact with your Serverless Pod. Pass in your Endpoint ID to the Endpoint URL and provide an operation.

### Endpoint URL
The Endpoint URL follows this structure:
- Base URL: `https://api.runpod.ai`
- API Version: `v2`
- Endpoint ID: `The ID of the Serverless point`
Example Endpoint URL: `https://api.runpod.ai/v2/{endpoint_id}/{operation}`

### Operations
You can perform various operations on the Serverless Endpoint using the following options:

- `run`: Start the Serverless Pod.
- `runsync`: Start the Serverless Pod synchronously.
- `status`: Check the status of the Serverless Pod.
- `cancel`: Cancel the operation of the Serverless Pod.
- `health`: Check the health status of the Serverless Pod.
- `purge-queue`: Purge the queue of the Serverless Pod.

Choose the appropriate operation based on your requirements.

## Are you good to go?
If you are still not getting it use this link on our GitHub that takes you through the whole process with Dockers and few Images on what should appear on your screen.[Here](https://github.com/SunbirdAI/sunbirdai-model-inferences/tree/main/deploy-docs)


## Part B: User-facing API high-level deployment steps
The user facing API is a FastAPI app that is deployed on Google Cloud Run. The following are the steps required to deploy it

**Step 1**: Setup the environment variables:
```bash
export APP=sunbird-ai-api
export TAG=gcr.io/sb-gcp-project-01/sunbird-ai-api
export PROJECT_ID=sb-gcp-project-01
export REGION=europe-west1
export PORT=8080
```

**Step 2**: Build and deploy the docker container:
- Build the container image and submit it to GCR
```bash
gcloud builds submit --tag $TAG
```

- Deploy to cloud run
```bash
gcloud run deploy $APP --image $TAG --platform managed --region $REGION --allow-unauthenticated
```

You can use the bash script to combine all the commands above to deploy the api in one go. Run the commands below

```sh
chmod u+x bin/deploy-api
./bin/deploy-api
```

## Part C: Azure Container Apps Deployment

The user-facing API can also be deployed to Azure Container Apps, a serverless container platform similar to Google Cloud Run. This section provides comprehensive instructions for deploying to Azure.

### Prerequisites

Before deploying to Azure Container Apps, ensure you have:

1. **Azure Subscription** with appropriate permissions (Contributor or Owner role)
2. **Azure CLI** installed and configured
   ```bash
   # Install Azure CLI (macOS)
   brew install azure-cli

   # Login to Azure
   az login

   # Set your subscription
   az account set --subscription "<subscription-id>"
   ```

3. **Terraform** installed (version >= 1.0)
   ```bash
   # Install Terraform (macOS)
   brew install terraform
   ```

4. **Git** access to the repository
5. **Docker** installed for local testing (optional)

### Infrastructure Provisioning with Terraform

The Azure infrastructure is managed using Terraform for reproducible deployments.

#### Step 1: Navigate to Terraform Directory

```bash
cd azure/terraform
```

#### Step 2: Configure Variables

Copy the example variables file and customize it:

```bash
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` with your specific values:

```hcl
location     = "eastus"              # Azure region
environment  = "prod"                # Environment name
project_name = "sunbird-ai"          # Project identifier
acr_sku      = "Basic"               # ACR tier (Basic, Standard, or Premium)
```

#### Step 3: Initialize Terraform

```bash
terraform init
```

#### Step 4: Review Infrastructure Plan

```bash
terraform plan
```

Review the output to ensure correct resources will be created.

#### Step 5: Provision Infrastructure

```bash
terraform apply --auto-approve
```

Type `yes` when prompted. This will create:
- Resource Group
- Azure Container Registry (ACR)
- Log Analytics Workspace
- Application Insights
- Container Apps Environment
- Container App (with placeholder image)

#### Step 6: Save Terraform Outputs

After successful deployment, save these outputs for GitHub Secrets configuration:

```bash
# Display all outputs
terraform output

# Save specific outputs
terraform output -raw resource_group_name
terraform output -raw acr_name
terraform output -raw container_app_name
terraform output -raw application_insights_connection_string
```

### GitHub Secrets Configuration

#### Step 1: Create Azure Service Principal

Create a service principal for GitHub Actions authentication:

```bash
# Get the resource group name from Terraform
RESOURCE_GROUP=$(terraform output -raw resource_group_name)

# Create service principal
az ad sp create-for-rbac \
  --name "sunbird-ai-github-actions" \
  --role Contributor \
  --scopes /subscriptions/<subscription-id>/resourceGroups/$RESOURCE_GROUP \
  --sdk-auth
```

Copy the JSON output and add it as GitHub Secret: **`AZURE_CREDENTIALS`**

#### Step 2: Add Required GitHub Secrets

In your GitHub repository settings (Settings → Secrets and variables → Actions), add the following secrets:

| Secret Name | Value | How to Get |
|-------------|-------|------------|
| `AZURE_CREDENTIALS` | Service Principal JSON | Output from Step 1 above |
| `AZURE_RESOURCE_GROUP` | Resource group name | `terraform output -raw resource_group_name` |
| `AZURE_ACR_NAME` | Container registry name | `terraform output -raw acr_name` |
| `AZURE_CONTAINER_APP_NAME` | Container app name | `terraform output -raw container_app_name` |
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | App Insights connection string | `terraform output -raw application_insights_connection_string` |

**Note**: All other application secrets (DATABASE_URL, REDIS_URL, etc.) should already be configured from existing GCP/Heroku deployments.

### Automated Deployment via GitHub Actions

Once GitHub Secrets are configured, deployments happen automatically.

#### Workflow Trigger

The Azure deployment workflow (`.github/workflows/deploy-api-azure.yml`) triggers on:
- Push to `azure-deploy` branch
- Pull request to `azure-deploy` branch

#### Deploy to Azure

```bash
# Switch to azure-deploy branch
git checkout azure-deploy

# Make your changes (or merge from main)
git merge main

# Push to trigger deployment
git push origin azure-deploy
```

#### Monitor Deployment

1. Go to your GitHub repository
2. Click on "Actions" tab
3. Watch the "Deploy to Azure Container Apps" workflow
4. Check deployment logs for any issues

### Manual Deployment

For manual deployments or testing, use the deployment script:

#### Step 1: Ensure Azure CLI is Authenticated

```bash
az login
az account set --subscription "<subscription-id>"
```

#### Step 2: Set Environment Variables (Optional)

```bash
export AZURE_RESOURCE_GROUP="rg-sunbird-ai-prod"
export AZURE_ACR_NAME="sunbirdaiacrprod"
export AZURE_CONTAINER_APP_NAME="ca-sunbird-ai-api-prod"
```

Or the script will use default values from Terraform.

#### Step 3: Run Deployment Script

```bash
chmod +x bin/deploy-api-azure.sh
./bin/deploy-api-azure.sh
```

The script will:
1. Build the Docker image from `Dockerfile.azure`
2. Tag it with the current git SHA
3. Push to Azure Container Registry
4. Update the Container App with the new image
5. Display the application URL

### Environment Variables Configuration

The Container App requires these environment variables (automatically set by GitHub Actions):

#### Core Application
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `ENVIRONMENT` - Set to "production"
- `PORT` - 8080 (default)

#### Firebase/GCP Integration
- `GOOGLE_APPLICATION_CREDENTIALS` - Path to firebase credentials
- Firebase configuration variables (PROJECT_ID, PRIVATE_KEY, CLIENT_EMAIL, etc.)

#### Monitoring
- `APPLICATIONINSIGHTS_CONNECTION_STRING` - Azure Application Insights

#### Additional Services
- SMTP configuration (SMTP_SERVER, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, MAIL_FROM)
- Frontend URLs (FRONTEND_LOCAL_URL, FRONTEND_PRODUCTION_URL)
- API keys (RUNPOD_API_KEY, HUGGING_FACE_TOKEN, WHATSAPP_TOKEN, etc.)

### Monitoring and Logging

#### View Application Logs

Using Azure CLI:

```bash
az containerapp logs show \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod \
  --follow
```

#### View Metrics in Azure Portal

1. Login to [Azure Portal](https://portal.azure.com)
2. Navigate to your Resource Group
3. Click on the Container App
4. View metrics, logs, and health status

#### Application Insights

Application Insights provides:
- Request tracking and performance metrics
- Dependency tracking (database, external APIs)
- Exception and error tracking
- Custom telemetry and logging
- Live metrics and alerts

Access Application Insights through Azure Portal or query logs using Kusto Query Language (KQL).

### Scaling Configuration

Azure Container Apps supports automatic scaling based on HTTP requests, CPU, memory, or custom metrics.

#### View Current Scaling Configuration

```bash
az containerapp show \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod \
  --query "properties.template.scale"
```

#### Update Scaling Rules

```bash
# Update min/max replicas
az containerapp update \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod \
  --min-replicas 1 \
  --max-replicas 10

# Add HTTP scaling rule
az containerapp update \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod \
  --scale-rule-name http-rule \
  --scale-rule-type http \
  --scale-rule-http-concurrency 50
```

### Troubleshooting

#### Issue: Authentication Failed

**Error**: `authentication failed` or `unauthorized`

**Solution**:
1. Verify Azure CLI is logged in: `az account show`
2. Check service principal permissions
3. Ensure AZURE_CREDENTIALS secret is correctly formatted

#### Issue: Container App Not Starting

**Error**: Container app revision in "Failed" state

**Solution**:
1. Check container logs: `az containerapp logs show --name <app-name> --resource-group <rg-name>`
2. Verify environment variables are set correctly
3. Check DATABASE_URL and REDIS_URL are accessible from Azure
4. Verify Firebase credentials file exists in the image

#### Issue: Database Connection Failed

**Error**: `could not connect to database` or `connection timeout`

**Solution**:
1. Verify DATABASE_URL is correct
2. Check database firewall rules allow Azure connections
3. If using Azure Database for PostgreSQL, add Container App outbound IPs to firewall

#### Issue: Image Push Failed

**Error**: `unauthorized: authentication required` when pushing to ACR

**Solution**:
```bash
# Re-authenticate to ACR
az acr login --name <acr-name>

# Or use admin credentials
az acr update --name <acr-name> --admin-enabled true
```

#### Issue: Terraform Apply Failed - Resource Providers Not Registered

**Error**: `MissingSubscriptionRegistration: The subscription is not registered to use namespace 'Microsoft.App'`

**Solution**:
Azure subscriptions don't have all resource providers enabled by default. Register the required providers:

```bash
# Register Microsoft.App (required for Container Apps)
az provider register --namespace Microsoft.App

# Register Microsoft.OperationalInsights (required for Log Analytics)
az provider register --namespace Microsoft.OperationalInsights

# Register Microsoft.ContainerRegistry (required for ACR)
az provider register --namespace Microsoft.ContainerRegistry

# Register Microsoft.Insights (required for Application Insights)
az provider register --namespace Microsoft.Insights

# Check registration status (wait until "Registered")
az provider show --namespace Microsoft.App --query "registrationState" -o tsv
az provider show --namespace Microsoft.OperationalInsights --query "registrationState" -o tsv
```

Registration takes 2-5 minutes. Once all show `Registered`, run `terraform apply` again.

**Verify all providers**:
```bash
az provider list --query "[?namespace=='Microsoft.App' || namespace=='Microsoft.OperationalInsights' || namespace=='Microsoft.ContainerRegistry' || namespace=='Microsoft.Insights'].{Namespace:namespace, State:registrationState}" -o table
```

#### Issue: Terraform Apply Failed - Resource Name Already Exists

**Error**: Resource name already exists or quota exceeded

**Solution**:
1. Check if resources already exist: `az resource list --resource-group <rg-name>`
2. Verify ACR name is globally unique (lowercase, no hyphens)
3. Check subscription quotas: `az vm list-usage --location <location>`

### Cost Optimization

#### Estimated Monthly Costs

| Resource | Configuration | Estimated Cost |
|----------|--------------|----------------|
| Container App | 0.5 vCPU, 1.0 Gi RAM, ~5M requests/month | $15-40 |
| ACR | Basic tier | $5 |
| Log Analytics | ~5GB/month | $2-5 |
| Application Insights | Included | $0 |
| **Total** | | **$22-50/month** |

#### Cost-Saving Tips

1. **Enable Scale-to-Zero**: Set `min-replicas = 0` for non-production environments
2. **Right-Size Resources**: Monitor actual usage and adjust CPU/memory allocation
3. **Log Retention**: Reduce Log Analytics retention period for dev/test environments
4. **ACR Cleanup**: Regularly remove old/unused images
5. **Set Budget Alerts**: Configure spending alerts in Azure Cost Management

```bash
# Set budget alert
az consumption budget create \
  --budget-name sunbird-ai-monthly-budget \
  --amount 100 \
  --time-grain Monthly \
  --resource-group rg-sunbird-ai-prod
```

### Security Best Practices

1. **Use Managed Identity**: Migrate from Service Principal to Managed Identity for production
2. **Enable Azure Key Vault**: Store secrets in Key Vault instead of environment variables
3. **Configure Virtual Network**: Integrate Container App with VNet for network isolation
4. **Enable Azure Front Door**: Add WAF (Web Application Firewall) protection
5. **Regular Updates**: Keep dependencies updated and scan for vulnerabilities
6. **Minimum Permissions**: Use principle of least privilege for service principals
7. **Enable Audit Logging**: Review activity logs regularly

### Updating the Application

#### Update via GitHub Actions (Recommended)

```bash
git checkout azure-deploy
# Make your changes
git commit -am "Update application"
git push origin azure-deploy
```

#### Update via Manual Deployment

```bash
./bin/deploy-api-azure.sh
```

#### Rollback to Previous Version

```bash
# List revisions
az containerapp revision list \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod

# Activate previous revision
az containerapp revision activate \
  --revision <previous-revision-name> \
  --resource-group rg-sunbird-ai-prod
```

### Useful Azure CLI Commands

```bash
# Check deployment status
az containerapp show \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod

# Get application URL
az containerapp show \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod \
  --query "properties.configuration.ingress.fqdn" \
  --output tsv

# View recent revisions
az containerapp revision list \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod \
  --output table

# Restart the container app
az containerapp revision restart \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod

# View environment variables
az containerapp show \
  --name ca-sunbird-ai-api-prod \
  --resource-group rg-sunbird-ai-prod \
  --query "properties.template.containers[0].env"
```

### Additional Resources

- [Azure Container Apps Documentation](https://learn.microsoft.com/en-us/azure/container-apps/)
- [Terraform Azure Provider](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs)
- [Azure CLI Reference](https://learn.microsoft.com/en-us/cli/azure/)
- [Application Insights Documentation](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [Terraform README](./azure/terraform/README.md) - Detailed infrastructure documentation

