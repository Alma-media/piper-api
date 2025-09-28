# Piper TTS API Server

A FastAPI-based HTTP server for Piper text-to-speech synthesis.

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
PIPER_MODELS_DIR="/home/alma/LLM/piper" uvicorn main:app --host 127.0.0.1 --port 8100 --reload
```

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
curl -o output.wav -X POST 'http://127.0.0.1:8100/synthesize/ru_RU-irina-medium' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Привет! Это проверка синтеза."}'

# With speed and volume adjustment using ru_RU-dmitri-medium voice
curl -o output.wav -X POST 'http://127.0.0.1:8100/synthesize/ru_RU-dmitri-medium' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Быстрая и громкая речь","rate":1.2,"volume":1.1}'

# Test with non-existent voice (returns 404)
curl -X POST 'http://127.0.0.1:8100/synthesize/non-existent-voice' \
  -H 'Content-Type: application/json' \
  -d '{"text":"This will fail"}'
```