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


