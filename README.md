# Piper TTS API Server

A FastAPI-based HTTP server for Piper text-to-speech synthesis.

## Quick Start with Docker

```bash
# Build and run with Docker Compose
git clone <your-repo>
cd piper-api
docker-compose up -d

# Test the API
curl 'http://localhost:8000/health'
curl -o test.wav -X POST 'http://localhost:8000/synthesize/ru_RU-irina-medium' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Hello from Piper TTS!"}'
```

## Setup

### Prerequisites
- Python 3.13+
- eSpeak NG data (usually at `/usr/share/espeak-ng-data`)
- Piper ONNX models with corresponding JSON config files

### Installation
```bash
python -m venv .venv
source .venv/bin/activate
uv sync
```

## Configuration

Set environment variables:

```bash
# Required: Directory containing Piper models (.onnx files with corresponding .json configs)
export PIPER_MODELS_DIR="/home/alma/LLM/piper"

# Optional: eSpeak NG data path (defaults to /usr/share/espeak-ng-data)
export ESPEAK_DATA_PATH=/usr/share/espeak-ng-data
```

The server will automatically discover all `.onnx` model files in the specified directory that have corresponding `.json` configuration files. Voice names will be derived from the model filenames (without the `.onnx` extension).

## Running

```bash
source .venv/bin/activate
PIPER_MODELS_DIR="/home/alma/LLM/piper" uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

## Docker

### Building the Docker Image

```bash
# Build the image
docker build -t piper-tts-api .

# Or with a specific tag
docker build -t piper-tts-api:latest .
```

### Running with Docker

```bash
# Run with models mounted from host directory
docker run -d \
  --name piper-tts \
  --restart unless-stopped \
  -p 8000:8000 \
  -v /home/alma/LLM/piper:/app/models:ro \
  piper-tts-api

# Run with custom port
docker run -d \
  --name piper-tts \
  --restart unless-stopped \
  -p 3000:8000 \
  -v /path/to/your/models:/app/models:ro \
  piper-tts-api

# Run interactively for debugging
docker run -it --rm \
  -p 8000:8000 \
  -v /home/alma/LLM/piper:/app/models:ro \
  piper-tts-api
```

### Docker Compose

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  piper-tts:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - /home/alma/LLM/piper:/app/models:ro
    environment:
      - PIPER_MODELS_DIR=/app/models
      - ESPEAK_DATA_PATH=/usr/share/espeak-ng-data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
```

Run with Docker Compose:

```bash
# Start the service
docker-compose up -d

# View logs
docker-compose logs -f

# Stop the service
docker-compose down
```

### Docker Usage Notes

**Volume Mounting**: The models directory must be mounted as a volume since the Docker image doesn't include the large model files. Mount your models directory to `/app/models` in the container.

**Health Check**: The container includes a health check that verifies the API is responding. You can check the health status with:

```bash
# Check container health
docker ps

# View health check logs
docker inspect --format='{{json .State.Health}}' piper-tts
```

**Logs**: View application logs:

```bash
# Docker run logs
docker logs piper-tts

# Docker compose logs
docker-compose logs -f piper-tts
```

**Troubleshooting**:
- Ensure your models directory contains `.onnx` files with corresponding `.json` configs
- Check that the mounted volume path is correct
- Verify port 8000 is not already in use on the host
- For permission issues, ensure the models directory is readable by the container

## API Endpoints

### Health Check
```bash
GET /health
```
Returns server status and available voices.

### List Voices
```bash
GET /voices
```
Returns mapping of voice names to model paths.

### Synthesize Speech
```bash
POST /synthesize/{voice_name}
Content-Type: application/json

{
  "text": "Text to synthesize",
  "speaker": 0,                  // optional, multi-speaker model index
  "noise_scale": 0.667,          // optional, generator noise (default 0.667)
  "length_scale": 1.0,           // optional, phoneme length (default 1.0)
  "noise_w": 0.8,                // optional, phoneme width noise (default 0.8)
  "sentence_silence": 0.2,       // optional, silence after sentences (default 0.2)
  "rate": 1.0,                   // optional, convenience for speed (1.05=faster, 0.95=slower)
  "volume": 1.0                  // optional, post-synthesis volume multiplier
}
```

The voice name is specified in the URL path. If the voice is not found, returns 404.

Returns WAV audio file.

## Examples

```bash
# Basic synthesis with ru_RU-irina-medium voice
curl -o output.wav -X POST 'http://127.0.0.1:8000/synthesize/ru_RU-irina-medium' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Привет! Это проверка синтеза."}'

# With speed and volume adjustment using ru_RU-dmitri-medium voice
curl -o output.wav -X POST 'http://127.0.0.1:8000/synthesize/ru_RU-dmitri-medium' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Быстрая и громкая речь","rate":1.2,"volume":1.1}'

# Test with non-existent voice (returns 404)
curl -X POST 'http://127.0.0.1:8000/synthesize/non-existent-voice' \
  -H 'Content-Type: application/json' \
  -d '{"text":"This will fail"}'
```