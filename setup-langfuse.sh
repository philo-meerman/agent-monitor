#!/bin/bash

set -e

echo "Setting up Langfuse v2 for AI agent observability..."

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
    git checkout v2
else
    echo "Langfuse directory already exists, skipping clone..."
    cd ../langfuse
fi

echo "Starting Langfuse with Docker Compose..."
docker compose up -d

echo ""
echo "Langfuse is starting up..."
echo "Access the UI at: http://localhost:3000"
echo ""
echo "To view logs: docker compose logs -f"
echo "To stop: docker compose down"
