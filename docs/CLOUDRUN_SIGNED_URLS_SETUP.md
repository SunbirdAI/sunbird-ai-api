# Cloud Run Signed URLs Setup Guide

This guide explains how to fix the signed URL generation error in Cloud Run production environments.

## The Problem

When running on Cloud Run, you may encounter this error:

```json
{
  "detail": "Failed to generate audio: you need a private key to sign credentials. The credentials you are currently using <class 'google.auth.compute_engine.credentials.Credentials'> just contains a token."
}
```

This happens because:
- Cloud Run uses **Compute Engine credentials** (token-based)
- Generating signed URLs requires a **service account with a private key** to sign the URL
- By default, Cloud Run doesn't have access to the private key

## The Solution: IAM-Based Signing

Instead of using a private key, we use **IAM-based signing** where Google's IAM service signs the URLs on your behalf.

### Step 1: Grant IAM Permissions to Cloud Run Service Account

Your Cloud Run service account needs the `iam.serviceAccountTokenCreator` role to sign URLs.

#### Option A: Using gcloud CLI (Recommended)

```bash
# Get your Cloud Run service account email
SERVICE_ACCOUNT=$(gcloud run services describe sunbird-ai-api \
  --region europe-west1 \
  --format 'value(spec.template.spec.serviceAccountName)')

echo "Service Account: ${SERVICE_ACCOUNT}"

# Grant the token creator role
gcloud iam service-accounts add-iam-policy-binding ${SERVICE_ACCOUNT} \
  --member="serviceAccount:${SERVICE_ACCOUNT}" \
  --role="roles/iam.serviceAccountTokenCreator"
```

#### Option B: Using Google Cloud Console

1. Go to [IAM & Admin > Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Find your Cloud Run service account (usually `PROJECT_NUMBER-compute@developer.gserviceaccount.com`)
3. Click on the service account
4. Go to the **PERMISSIONS** tab
5. Click **GRANT ACCESS**
6. Add the same service account email as a principal
7. Assign the role: **Service Account Token Creator** (`roles/iam.serviceAccountTokenCreator`)
8. Click **SAVE**

### Step 2: Set Environment Variable in Cloud Run

Set the `GCP_SERVICE_ACCOUNT_EMAIL` environment variable in your Cloud Run service:

```bash
# Get the service account email
SERVICE_ACCOUNT=$(gcloud run services describe sunbird-ai-api \
  --region europe-west1 \
  --format 'value(spec.template.spec.serviceAccountName)')

# Update Cloud Run with the environment variable (adds/updates without removing others)
gcloud run services update sunbird-ai-api \
  --region europe-west1 \
  --update-env-vars GCP_SERVICE_ACCOUNT_EMAIL=${SERVICE_ACCOUNT}
```

> **Important:** Use `--update-env-vars` (not `--set-env-vars`) to add/update a single variable without removing your existing environment variables. The `--set-env-vars` flag replaces ALL environment variables.

**Alternative: Set via Cloud Console**

1. Go to [Cloud Run](https://console.cloud.google.com/run)
2. Click on your service (`sunbird-ai-api`)
3. Click **EDIT & DEPLOY NEW REVISION**
4. Go to **Variables & Secrets** tab
5. Add environment variable:
   - **Name**: `GCP_SERVICE_ACCOUNT_EMAIL`
   - **Value**: Your service account email (e.g., `123456789-compute@developer.gserviceaccount.com`)
6. Click **DEPLOY**

### Step 3: Verify the Fix

After deploying, test the `/tasks/modal/tts` endpoint:

```bash
curl -X POST https://your-cloudrun-url.run.app/tasks/modal/tts \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Hello world",
    "language": "en",
    "response_mode": "url"
  }'
```

You should now receive a signed URL without errors.

---

## How It Works

### Before (Failed)

```
Cloud Run → Storage Client → ❌ No private key → Error
```

The storage client tried to sign URLs using compute engine credentials, which don't contain a private key.

### After (Fixed)

```
Cloud Run → Storage Client → IAM Service → ✅ Signed URL
```

1. Storage client calls `generate_signed_url()` with `service_account_email` parameter
2. Google Cloud IAM service signs the URL using the service account's private key (stored securely by Google)
3. Signed URL is returned

---

## Code Changes

The storage service was updated to support IAM-based signing:

### Updated: `app/services/storage_service.py`

```python
# Constructor now accepts service_account_email
def __init__(
    self,
    bucket_name: Optional[str] = None,
    project_id: Optional[str] = None,
    service_account_email: Optional[str] = None,
):
    # ...
    self._service_account_email = service_account_email or os.getenv("GCP_SERVICE_ACCOUNT_EMAIL")

# generate_upload_url and generate_download_url now use IAM signing
signing_kwargs = {
    "version": "v4",
    "expiration": timedelta(minutes=expiry_minutes),
    "method": "PUT",
    "content_type": content_type,
}

# Add service account email for IAM signing if available
if self._service_account_email:
    signing_kwargs["service_account_email"] = self._service_account_email

signed_url = blob.generate_signed_url(**signing_kwargs)
```

---

## Environment Variables Summary

| Variable | Required | Description | Example |
|----------|----------|-------------|---------|
| `GCP_SERVICE_ACCOUNT_EMAIL` | **Yes** (Cloud Run) | Service account email for IAM signing | `123456789-compute@developer.gserviceaccount.com` |
| `AUDIO_CONTENT_BUCKET_NAME` | Yes | GCS bucket name | `sb-asr-audio-content-sb-gcp-project-01` |
| `GCP_PROJECT_ID` | No | GCP project ID (auto-detected in Cloud Run) | `your-project-id` |

---

## Troubleshooting

### Error: "Permission denied"

**Problem**: Service account doesn't have permission to sign URLs.

**Solution**: Grant the `roles/iam.serviceAccountTokenCreator` role (see Step 1).

### Error: "Service account not found"

**Problem**: `GCP_SERVICE_ACCOUNT_EMAIL` is incorrect or not set.

**Solution**:
1. Get the correct service account email:
   ```bash
   gcloud run services describe sunbird-ai-api \
     --region europe-west1 \
     --format 'value(spec.template.spec.serviceAccountName)'
   ```
2. Set it as an environment variable in Cloud Run (see Step 2).

### Error: Still seeing "you need a private key" error

**Problem**: Environment variable not set or code not using it.

**Solution**:
1. Verify `GCP_SERVICE_ACCOUNT_EMAIL` is set in Cloud Run
2. Check Cloud Run logs to see if the variable is being read
3. Redeploy the service after setting the environment variable

---

## Security Considerations

### ✅ Best Practices

- **IAM-based signing is more secure** than storing service account keys
- Service account keys are never exposed or stored in the container
- Cloud Run service account has minimal required permissions
- Signed URLs expire after the specified time (default: 30 minutes)

### ⚠️ Important Notes

- The Cloud Run service account needs `roles/iam.serviceAccountTokenCreator` on **itself**
- The service account also needs `roles/storage.objectCreator` and `roles/storage.objectViewer` on the bucket
- Never commit service account key files to version control
- Use Cloud Run's built-in service accounts when possible

---

## Alternative: Using Service Account Key File (Not Recommended)

If you absolutely must use a service account key file:

1. **Create a service account key**:
   ```bash
   gcloud iam service-accounts keys create key.json \
     --iam-account=SERVICE_ACCOUNT_EMAIL
   ```

2. **Store as Cloud Run secret**:
   ```bash
   gcloud secrets create gcp-storage-key --data-file=key.json
   ```

3. **Mount secret in Cloud Run**:
   ```bash
   gcloud run services update sunbird-ai-api \
     --update-secrets=GOOGLE_APPLICATION_CREDENTIALS=/secrets/gcp-storage-key:latest
   ```

⚠️ **This approach is NOT recommended** because:
- Service account keys are security risks if leaked
- Keys don't expire automatically
- IAM-based signing is simpler and more secure

---

## References

- [Google Cloud: Signed URLs with IAM](https://cloud.google.com/storage/docs/access-control/signed-urls#signing-iam)
- [Service Account Token Creator Role](https://cloud.google.com/iam/docs/service-accounts#token-creator-role)
- [Cloud Run Service Identity](https://cloud.google.com/run/docs/securing/service-identity)
- [Python Storage Client: generate_signed_url](https://googleapis.dev/python/storage/latest/blobs.html#google.cloud.storage.blob.Blob.generate_signed_url)

---

## Quick Reference Commands

```bash
# Get Cloud Run service account
gcloud run services describe sunbird-ai-api \
  --region europe-west1 \
  --format 'value(spec.template.spec.serviceAccountName)'

# Grant IAM permissions
gcloud iam service-accounts add-iam-policy-binding SERVICE_ACCOUNT_EMAIL \
  --member="serviceAccount:SERVICE_ACCOUNT_EMAIL" \
  --role="roles/iam.serviceAccountTokenCreator"

# Set environment variable (adds/updates without removing others)
# IMPORTANT: Use --update-env-vars (not --set-env-vars which replaces ALL variables)
gcloud run services update sunbird-ai-api \
  --region europe-west1 \
  --update-env-vars GCP_SERVICE_ACCOUNT_EMAIL=SERVICE_ACCOUNT_EMAIL

# View current environment variables
gcloud run services describe sunbird-ai-api \
  --region europe-west1 \
  --format 'value(spec.template.spec.containers[0].env)'

# View Cloud Run logs
gcloud run services logs read sunbird-ai-api \
  --region europe-west1 \
  --limit 50
```
