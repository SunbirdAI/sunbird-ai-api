# Sunbird AI API

![coverage badge](coverage.svg)
![tests](https://github.com/SunbirdAI/sunbird-ai-api/actions/workflows/build-test.yml/badge.svg)

This repository contains code for the publicly accessible Sunbird AI APIs.

To get started using the API, [view the tutorial](docs/tutorial.md).
To get started with the sunflower model, [view the sunflower API docs](docs/sunflower_api_docs.md).

## Getting started locally on Windows

#### Ensure virtualization is enabled on your computer

This is required because CPU virtualization is needed for Windows to emulate Linux. For more on enabling [virtualization](https://www.ninjaone.com/blog/enable-hyper-v-on-windows/).

#### Ensure your windows is fully updated.

Install [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) (Windows Subsystem for Linux). This is required because redis is not officially supported on Windows.

### Downloading, Setting Up, and Configuring WSL on Windows
-  Open PowerShell as an Administrator and run the following command to enable WSL:
    ```powershell
    wsl --install
    ```
-  Restart your computer if prompted.
-  Once the system restarts, set up your Linux distribution (e.g., Ubuntu) from the Microsoft Store.

### After successfully installing `wsl`:

- Press windows button and in the search bar type `windows features on or off`
- Click on `Turn Windows features on or off` and a pop-up window will appear
![features2](features2.png)
- Ensure option `Windows Subsystem for Linux` is checked

  ![features](features.png)

- Restart your computer and launch Ubuntu

### Cloning the API Repository Locally on Your Windows Machine
- Open your WSL terminal (e.g., Ubuntu).
- Navigate to the directory where you want to clone the repository:
  ```bash
  cd /mnt/c/your-directory
  ```
- Clone the Sunbird AI API repository:
  ```bash
  git clone https://github.com/SunbirdAI/sunbird-ai-api.git
  ```

- Continue with `Getting started locally on Linux/macOS`

## Getting started locally on Linux/macOS
To run the app locally:
- Create and activate a local environment

    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```
- Install the requirements:
    ```bash
    pip install -r requirements.txt
    ```
- Set the environment variables in a `.env` file, the following variables are required:
    ```
    SECRET_KEY
    DATABASE_URL
    RUNPOD_API_KEY
    REDIS_URL
    RUNPOD_ENDPOINT
    AUDIO_CONTENT_BUCKET_NAME
    ```
    **NB: Reach out to the engineering team to get these environment variables.**
 
 
 ### Install [Redis](https://redis.io/), this is required for the Rate Limiting functionality.
```bash
sudo apt update && sudo apt install redis-server
```
- Start the Redis sever:
    ```bash
    sudo service redis-server start
    ```
- Verify that Redis is running:

    ```bash
    redis-cli ping
    ```


### Setting Up and Configuring PostgreSQL Server
- Install PostgreSQL:
    ```bash
  sudo apt-get install postgresql postgresql-contrib
  ```
- Start the PostgreSQL service:
  ```bash
  sudo service postgresql start
  ```

-  Switch to the PostgreSQL user:
   ```bash
   sudo -i -u postgres
     ```

-  Open the PostgreSQL interactive terminal:
   ```bash
   psql
    ```

### Install [tailwind css](https://tailwindcss.com/docs/installation).
- Run tailwind in a separate terminal tab:

    ```bash
    npx tailwindcss -i ./app/static/input.css -o ./app/static/output.css --watch
    ```
This step is only necessary if you're going to make changes to the frontend code.

### Creating PostgreSQL Database and Running Alembic Migrations
- Create a new database:
    ```sql
    CREATE DATABASE sunbird_ai;
    ```
-  Exit the PostgreSQL interactive terminal:
    ```sql
    \q
    ```
- Navigate to the API repository directory and run Alembic migrations:
    ```bash
    cd your-directory/sunbird-ai-api
    alembic upgrade head
    ```
- Run the app:
    ```bash
    uvicorn app.api:app --reload
    ```

### Running the migrations with alembic:
- After making a change to the models, run the command below to make the migrations:
    ```bash
    alembic revision --autogenerate -m 'message'
    ```

- Check the created migration file in `app/alembic/versions` to ensure it does what's expected.
- Apply the migration with:
    ```bash
    alembic upgrade head
    ```


## Deployment
The app is deployed on Google Cloud Run and is backed by PostgreSQL DB hosted in Google Cloud SQL.

## Setting up Workload Identity Federation (WIF) for GitHub Actions

To securely deploy from GitHub Actions to Google Cloud, set up Workload Identity Federation (WIF) as follows:

### 1. Prerequisites
- You must have Owner or IAM Admin permissions on your GCP project.
- Install the [gcloud CLI](https://cloud.google.com/sdk/docs/install).
- Enable the following APIs:
  - IAM API
  - IAM Credentials API
  - Security Token Service API

### 2. Run the Setup Script
A helper script is provided to automate WIF setup:

```bash
bin/setup_wif.sh
```
This script will:
- Create a Workload Identity Pool and OIDC provider for GitHub Actions
- Restrict access to your repository (and optionally branch)
- Create a service account and bind the WIF pool to it
- Output the values you need for GitHub secrets

### 3. Add GitHub Secrets
After running the script, add the following secrets to your GitHub repository (Settings > Secrets and variables > Actions):
- `WORKLOAD_IDENTITY_PROVIDER` (output by the script)
- `GCP_SA_EMAIL` (output by the script)
- `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_PROJECT_REPO`, `APP_NAME` (as needed for your deployment)

### 4. Configure GitHub Actions
The provided workflow in `.github/workflows/deploy-api.yml` is already set up to use WIF. It authenticates using the secrets above and deploys to Cloud Run.

For more details, see:
- [Google Cloud: Workload Identity Federation with deployment pipelines](https://cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines)
- [Google GitHub Actions Auth](https://github.com/google-github-actions/auth#setting-up-workload-identity-federation)

---
## Other docs
- Checkout the [System design document](https://github.com/SunbirdAI/sunbird-docs/blob/main/06-design-docs/language/API_Framework.md) (you need to part of the Sunbird organization to view this).
- Checkout the [Deployment Guide](https://github.com/SunbirdAI/sunbird-ai-api/blob/main/docs/api-deployment-docs.md).
