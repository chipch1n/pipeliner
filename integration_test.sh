#!/usr/bin/env bash
set -eo pipefail

docker compose up -d --build
trap 'docker compose down' EXIT

python -m pytest ./backend/tests/integration | tee integration-tests.log