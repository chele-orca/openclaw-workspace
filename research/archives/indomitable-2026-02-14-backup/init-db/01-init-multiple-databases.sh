#!/bin/bash
set -e

# This script creates multiple databases in PostgreSQL
# Place this in ./init-db/ folder

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" <<-EOSQL
    -- Create n8n database and user
    CREATE DATABASE n8n;
    CREATE USER n8n WITH PASSWORD '${POSTGRES_PASSWORD}';
    GRANT ALL PRIVILEGES ON DATABASE n8n TO n8n;

    -- Create sec_filings database and user
    CREATE DATABASE sec_filings;
    CREATE USER sec_user WITH PASSWORD '${POSTGRES_PASSWORD}';
    GRANT ALL PRIVILEGES ON DATABASE sec_filings TO sec_user;
EOSQL

# Connect to n8n database and grant schema privileges
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname=n8n <<-EOSQL
    -- Grant schema privileges to n8n user
    GRANT ALL ON SCHEMA public TO n8n;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO n8n;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO n8n;
EOSQL

# Connect to sec_filings database and grant schema privileges
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname=sec_filings <<-EOSQL
    -- Grant schema privileges to sec_user
    GRANT ALL ON SCHEMA public TO sec_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO sec_user;
    ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO sec_user;
EOSQL

echo "Multiple databases created successfully!"
