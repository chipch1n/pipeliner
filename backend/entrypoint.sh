#!/bin/sh

LIQUIBASE_URL="jdbc:postgresql://$DB_HOST:$DB_PORT/$DB_NAME"

echo "Running migration..."
liquibase \
  --url="$LIQUIBASE_URL" \
  --username="$DB_USER" \
  --password="$DB_PASSWORD" \
  --driver=org.postgresql.Driver \
  --changelog-file=/app/liquibase/db.changelog-master.yaml \
  update

echo "Starting application..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000