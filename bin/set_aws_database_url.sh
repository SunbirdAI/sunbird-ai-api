#!/bin/bash

# Ensure the script exits if any command fails
set -e

echo "setting AWS DATABASE URL"
AWS_RDS_AURORA_USERNAME=postgres
AWS_RDS_AURORA_PASSWORD=password_here
AWS_RDS_AURORA_ENDPOINT=sunbirdai-api-db.cluster-cuzp9mi8kwc3.eu-west-1.rds.amazonaws.com

export AWS_PROD_DATABASE_CONNECTION_URL="postgresql+asyncpg://postgres:${AWS_RDS_AURORA_PASSWORD}@${AWS_RDS_AURORA_ENDPOINT}:5432/sunbirdaiapidb"
echo $AWS_PROD_DATABASE_CONNECTION_URL

# psql -h sunbirdai-api-db.cluster-cuzp9mi8kwc3.eu-west-1.rds.amazonaws.com -U postgres -d sunbirdaiapidb -p 5432
# psql -h sunbird-noise-db.cuzp9mi8kwc3.eu-west-1.rds.amazonaws.com -U postgres -d postgres -p 5432
# pg_restore --verbose --clean --no-acl --no-owner -h sunbirdai-api-db.cluster-cuzp9mi8kwc3.eu-west-1.rds.amazonaws.com -U postgres -d sunbirdaiapidb latest.dump

