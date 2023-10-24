There are 2 major components of the API deployment:
- The "inference server" which connects the models to hardware resources. (Currently deployed to Vertex AI)
  - [inference-server repo](https://github.com/SunbirdAI/api-inference-server)
- The user-facing API. (currently deployed on Cloud Run)
  - [sunbird-ai-api repo](https://github.com/SunbirdAI/sunbird-ai-api)

### Inference-server high-level deployment steps
- Build the "inference-server" container. (try to see if you can use gcloud builds for this)
- Create a repository on "Artifact Registry" or "Container Registry". 
- Push the container to "Artifact Registry" or "Container Registry".
- Create a Vertex AI "Model" that uses the custom container.
- Deploy the "Model" to an endpoint.
- Get online predictions from the endpoint.

**Steps 1-3**: Build "Inference-server"
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
- **TODO**: Programmatically extract the `ENDPOINT_ID` and `MODEL_ID` 
- This is failing (model deployment fails). Things to try next:
	- Test locally on Github codespaces (or GCP workstations)
	- Try to download the models onto disk and fetch from there (instead of fetching them from HuggingFace)
	- Deploying the old model works. (Difference there is that I fetch the ASR model from disk)
- More resources to checkout:
	- [online prediction logging](https://cloud.google.com/vertex-ai/docs/predictions/online-prediction-logging)
	- [gcloud ai endpoints deploy-model.](https://cloud.google.com/sdk/gcloud/reference/ai/endpoints/deploy-model#--accelerator)
	- 
### API high-level deployment steps
- Build the docker container.
- Deploy the built container.
