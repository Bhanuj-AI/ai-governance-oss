#!/usr/bin/env bash
set -euo pipefail

echo
echo "Starting AI Governance Control Plane..."
docker compose up --build -d

echo
echo "AI Governance Control Plane is running."
echo "Studio: http://localhost:3000"
echo "API:    http://localhost:8000"
