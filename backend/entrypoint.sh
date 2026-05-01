#!/bin/sh

LIQUIBASE_URL="jdbc:postgresql://db:5432/pipeliner"
LIQUIBASE_USER="postgres"
LIQUIBASE_PASSWORD="postgres"

echo "Running migration..."
liquibase \
  --url="$LIQUIBASE_URL" \
  --username="$LIQUIBASE_USER" \
  --password="$LIQUIBASE_PASSWORD" \
  --driver=org.postgresql.Driver \
  --changelog-file=/app/liquibase/db.changelog-master.yaml \
  update

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000