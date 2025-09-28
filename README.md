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
# Required: JSON mapping of voice names to model paths
export PIPER_VOICES='{"ru_irina":"/path/to/ru_RU-irina-medium.onnx", "ru_dmitri":"/path/to/ru_RU-dmitri-medium.onnx"}'

# Optional: default voice (defaults to first voice in PIPER_VOICES)
export PIPER_DEFAULT_VOICE=ru_irina

# Optional: eSpeak NG data path (defaults to /usr/share/espeak-ng-data)
export ESPEAK_DATA_PATH=/usr/share/espeak-ng-data
```

## Running

```bash
source .venv/bin/activate
PIPER_VOICES='{"ru_irina":"/home/alma/LLM/piper/ru_RU-irina-medium.onnx", "ru_dmitri":"/home/alma/LLM/piper/ru_RU-dmitri-medium.onnx"}' uvicorn main:app --host 127.0.0.1 --port 8100 --reload
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
POST /synthesize
Content-Type: application/json

{
  "text": "Text to synthesize",
  "voice": "ru_irina",           // optional, uses default if not specified
  "speaker": 0,                  // optional, multi-speaker model index
  "noise_scale": 0.667,          // optional, generator noise (default 0.667)
  "length_scale": 1.0,           // optional, phoneme length (default 1.0)
  "noise_w": 0.8,                // optional, phoneme width noise (default 0.8)
  "sentence_silence": 0.2,       // optional, silence after sentences (default 0.2)
  "rate": 1.0,                   // optional, convenience for speed (1.05=faster, 0.95=slower)
  "volume": 1.0                  // optional, post-synthesis volume multiplier
}
```

Returns WAV audio file.

## Examples

```bash
# Basic synthesis
curl -o output.wav -X POST 'http://127.0.0.1:8100/synthesize' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Привет! Это проверка синтеза.","voice":"ru_irina"}'

# With speed and volume adjustment
curl -o output.wav -X POST 'http://127.0.0.1:8100/synthesize' \
  -H 'Content-Type: application/json' \
  -d '{"text":"Быстрая и громкая речь","voice":"ru_dmitri","rate":1.2,"volume":1.1}'
```