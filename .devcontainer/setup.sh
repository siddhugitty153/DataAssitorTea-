#!/bin/bash
set -e

echo "=== Installing Python dependencies ==="
pip install -r requirements.txt

echo "=== Building Sandbox Docker Image ==="
docker build -t data-sandbox ./sandbox

echo "=== Installing Ollama ==="
curl -fsSL https://ollama.com/install.sh | sh

echo "=== Starting Ollama in background ==="
ollama serve &
OLLAMA_PID=$!

echo "=== Waiting for Ollama to start ==="
sleep 5

echo "=== Pulling Open-Source Models ==="
echo "Pulling LLM (llama3.2)..."
ollama pull llama3.2
echo "Pulling Embedding Model (nomic-embed-text)..."
ollama pull nomic-embed-text

echo "=== Setup Complete! ==="
# We can kill the background ollama now, as Codespaces will manage background processes or 
# the user will just have it running. Actually, since this is postCreateCommand, 
# the background process might die. In Codespaces, to keep a service running, 
# it's better to add it to a postStartCommand.
kill $OLLAMA_PID
