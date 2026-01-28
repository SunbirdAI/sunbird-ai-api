# Docker Quick Start Guide

Quick reference for Docker operations with Sunbird AI API.

## Quick Commands

### Using Makefile (Recommended)

```bash
# Build the image
make docker-build

# Run with docker-compose (includes PostgreSQL)
make docker-compose-up

# View logs
make docker-compose-logs

# Stop everything
make docker-compose-down

# Push to Google Container Registry
make docker-push PROJECT=your-gcp-project-id
```

### Using Docker CLI

```bash
# Build
docker build -t sunbird-ai-api .

# Run
docker run -p 8000:8080 --env-file .env sunbird-ai-api

# Stop
docker stop sunbird-api
```

## Local Development

### Option 1: Docker Compose (Recommended)

```bash
# Start API + PostgreSQL
docker-compose up -d

# Your API is now at:
http://localhost:8000

# View API docs:
http://localhost:8000/docs
```

### Option 2: Docker Only

```bash
# Build
make docker-build

# Run (requires external database)
make docker-run
```

## Deploying to GCP Cloud Run

### Step 1: Build and Push

```bash
# Build the image
docker build -t sunbird-ai-api .

# Tag for GCR
docker tag sunbird-ai-api gcr.io/PROJECT_ID/sunbird-ai-api

# Push to GCR
docker push gcr.io/PROJECT_ID/sunbird-ai-api

# OR use the Makefile
make docker-push PROJECT=your-project-id
```

### Step 2: Deploy

```bash
gcloud run deploy sunbird-ai-api \
  --image gcr.io/PROJECT_ID/sunbird-ai-api \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars DATABASE_URL=postgresql://... \
  --memory 1Gi \
  --cpu 2
```

## Environment Variables

### Required

```bash
DATABASE_URL=postgresql+asyncpg://user:pass@host/db
```

### Optional

```bash
PORT=8080                    # Default: 8080
WORKERS=4                    # Default: 4
ENVIRONMENT=production       # Default: production
LOG_LEVEL=info              # Default: info
```

## Troubleshooting

### Check Container Status

```bash
docker ps                    # Running containers
docker ps -a                 # All containers
docker logs sunbird-api      # View logs
```

### Health Check

```bash
# Check if API is healthy
curl http://localhost:8000/health
```

### Shell Access

```bash
# Access container shell
docker exec -it sunbird-api /bin/bash

# Or use Makefile
make docker-shell
```

### Clean Up

```bash
# Stop and remove containers
make docker-stop

# Remove all stopped containers
docker container prune

# Remove unused images
docker image prune

# Remove everything (careful!)
docker system prune -a
```

## Common Issues

### Port Already in Use

```bash
# Find process using port 8000
lsof -i :8000

# Kill the process
kill -9 <PID>
```

### Database Connection Failed

```bash
# Check if database is running
docker-compose ps

# Restart database
docker-compose restart db
```

### Build Fails

```bash
# Clear build cache
docker builder prune

# Build without cache
docker build --no-cache -t sunbird-ai-api .
```

## Performance Tips

1. **Use docker-compose for local dev** - Includes PostgreSQL
2. **Don't rebuild unnecessarily** - Use layer caching
3. **Clean up regularly** - Remove unused images/containers
4. **Monitor resource usage** - `docker stats`

## Security Notes

- ✅ Container runs as non-root user (appuser)
- ✅ No secrets in image (use Cloud Run secrets)
- ✅ Minimal attack surface (only runtime dependencies)
- ✅ Regular security scans: `docker scan sunbird-ai-api`

## More Information

- Full documentation: [DOCKER_IMPROVEMENTS.md](DOCKER_IMPROVEMENTS.md)
- Makefile guide: [MAKEFILE_GUIDE.md](MAKEFILE_GUIDE.md)
- GCP Cloud Run docs: https://cloud.google.com/run/docs
