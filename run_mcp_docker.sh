#!/bin/bash

# Script to run the MCP server in Docker
# Usage: ./run_mcp_docker.sh [path/to/models]

MODELS_DIR=${1:-"./models"}

if [ ! -d "$MODELS_DIR" ]; then
    echo "Error: Models directory '$MODELS_DIR' does not exist"
    echo "Usage: $0 [path/to/models]"
    exit 1
fi

echo "Starting Piper TTS MCP Server in Docker..."
echo "Models directory: $MODELS_DIR"

# Build the Docker image if it doesn't exist
if ! docker image inspect piper-mcp:latest >/dev/null 2>&1; then
    echo "Building Docker image..."
    docker build -f Dockerfile.mcp -t piper-mcp:latest .
fi

# Run the MCP server container
docker run -i --rm \
    -v "$(realpath "$MODELS_DIR"):/app/models:ro" \
    piper-mcp:latest
