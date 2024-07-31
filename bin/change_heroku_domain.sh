#!/bin/bash

set -e

# Login to Heroku CLI
heroku login

# Remove old domain
heroku domains:remove api.sunbird.ai -a sunbirdai-api

# Add new domain
heroku domains:add api-staging.sunbird.ai -a sunbirdai-api

# View domains to get DNS target
heroku domains -a sunbirdai-api
