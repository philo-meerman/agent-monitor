#!/bin/bash

set -euo pipefail

echo "Setting up Langfuse v3 for AI agent observability..."

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "Error: Docker is not running. Please start Docker Desktop first."
    exit 1
fi

# Clone Langfuse if not already present
if [ ! -d "../langfuse" ]; then
    echo "Cloning Langfuse repository..."
    cd ..
    git clone https://github.com/langfuse/langfuse.git
    cd langfuse
else
    echo "Langfuse directory already exists, skipping clone..."
    cd ../langfuse
fi

# Copy v3 docker-compose if not exists
if [ ! -f "docker-compose.v3.yml" ]; then
    echo "docker-compose.v3.yml not found. Please ensure you have the v3 compose file."
    exit 1
fi

echo "Starting Langfuse v3 with Docker Compose..."
docker compose -f docker-compose.v3.yml up -d

echo ""
echo "Langfuse v3 is starting up..."
echo "Access the UI at: http://localhost:3000"
echo "MinIO Console at: http://localhost:9090"
echo ""
echo "To view logs: docker compose -f docker-compose.v3.yml logs -f"
echo "To stop: docker compose -f docker-compose.v3.yml down"
