# Deployment Guide for the Sunbird AI API
There are 2 major components of the API deployment:
- The "inference server" which connects the models to hardware resources. (Currently deployed to Vertex AI)
  - [inference-server repo](https://github.com/SunbirdAI/api-inference-server)
- The user-facing API. (currently deployed on Cloud Run)
  - [sunbird-ai-api repo](https://github.com/SunbirdAI/sunbird-ai-api)

## Part A: Inference-server high-level deployment steps
- Build the "inference-server" container. (try to see if you can use gcloud builds for this)
- Create a repository on "Artifact Registry" or "Container Registry". 
- Push the container to "Artifact Registry" or "Container Registry".
- Create a Vertex AI "Model" that uses the custom container.
- Deploy the "Model" to an endpoint.
- Get online predictions from the endpoint.

**Steps 1-3**: Build "Inference-server"
You can first test that it is working locally by:
- Build and run the container locally (can use Cloud Workstations to avoid long download times):
```bash
docker build -t my-docker-api .
docker run -it -p 8080:8080 my-docker-api
```
- [Use custom-container docs](https://cloud.google.com/vertex-ai/docs/predictions/use-custom-container).
```bash
# Environment variables
export APP=api-inference-server
export TAG="gcr.io/sb-gcp-project-01/$APP"
export REGION=europe-west1

# Use Google Cloud Build to build the container (and push it )
gcloud builds submit --tag $TAG
```
**Steps 4**: Create a Vertex AI "Model" from the container above
```bash
gcloud ai models upload \
--region=$REGION \
--display-name=api-inference-server-model \
--container-image-uri=$TAG \
--container-health-route="/isalive" \
--container-predict-route="/predict"
```
Note: add a `--parent-model` field when updating the model.
**Steps 5**: Deploy the "Model" to an endpoint
- Create an endpoint:
```bash
gcloud ai endpoints create \
--region=$REGION \
--display-name=api-inference-server-endpoint
```
- Retrieve the endpoint ID
```bash
gcloud ai endpoints list \
--region=$REGION \
--filter=display_name=api-inference-server-endpoint
```
(note: can use the same method above to get the MODEL_ID)
- Deploy the model:
```bash
gcloud ai endpoints deploy-model $ENDPOINT_ID \
--region=$REGION \
--model=$MODEL_ID \
--display-name=api-inference-server-model \
--machine-type=n1-standard-4 \
--accelerator=count=1,type=nvidia-tesla-t4 \
--min-replica-count=1 \
--max-replica-count=1 \
--traffic-split=0=100
```
- [deploy-model docs ](https://cloud.google.com/sdk/gcloud/reference/ai/endpoints/deploy-model)
- Get the options for [machine types here](https://cloud.google.com/vertex-ai/docs/predictions/configure-compute).
- Options for `accelerator-count`: `nvidia-tesla-k80`,  `nvidia-tesla-p100`, `nvidia-tesla-t4`.
- [Pricing](https://cloud.google.com/vertex-ai/pricing#custom-trained_models)


#### GCP Services used
The API inference server uses the following GCP services:
- **_Cloud Workstations_**: For testing the container locally. (We use this because the models are very heavy to test directly on our machines.)
- **_Google Container Registry (GCR)_**: For storing the built containers.
- **_Google Cloud Builds_**: For building the docker image remotely and uploading the 
- **_Vertex AI models_**: Creating a deployable model from the container.
- **_Vertex AI endpoints_**: Actual deployment that provides hardware resources to the models and exposes the REST endpoint used by the user-facing API.

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

**NOTE**:
If you deploy to a different Vertex AI endpoint in "Part A: Step 5" above, then on cloud run, you'll need to update the `ENDPOINT_ID` environment variable to point to the new endpoint's ID.
This can be done on the GCP console.
