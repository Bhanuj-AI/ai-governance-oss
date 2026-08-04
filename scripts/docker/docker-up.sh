#!/usr/bin/env bash
set -euo pipefail

echo
echo "Starting Kavach..."
docker compose up --build -d

echo
echo "Kavach is running."
echo "Studio: http://localhost:3000"
echo "API:    http://localhost:8000"
