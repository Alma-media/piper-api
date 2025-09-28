import io
import json
import os
import wave
from functools import lru_cache
from typing import Dict, Optional

from fastapi import FastAPI, Body, HTTPException
from fastapi.responses import Response, JSONResponse
from pydantic import BaseModel, Field

# -------- Config via env vars --------
# Directory containing Piper models (.onnx files with corresponding .json configs)
# Example: export PIPER_MODELS_DIR="/home/alma/LLM/piper"
PIPER_MODELS_DIR = os.getenv("PIPER_MODELS_DIR", "./models")

# eSpeak NG data path (needed by Piper phonemizer)
# On Arch: /usr/share/espeak-ng-data
ESPEAK_DATA_PATH = os.getenv("ESPEAK_DATA_PATH", "/usr/share/espeak-ng-data")

# If you want to force CPU/GPU at the Python layer (optional; Piper mostly uses ONNXRuntime options)
# For Piper Python lib this is not strictly required; leaving here for completeness.
USE_CUDA = os.getenv("PIPER_USE_CUDA", "0") == "1"

# -------- Data models --------
class SynthesisRequest(BaseModel):
    text: str = Field(..., description="Plain UTF-8 text to synthesize")
    # Optional per-request voice params
    speaker: Optional[int] = Field(None, description="Multi-speaker index (if model supports)")
    noise_scale: Optional[float] = Field(None, description="Generator noise (default 0.667)")
    length_scale: Optional[float] = Field(None, description="Phoneme length (default 1.0)")
    noise_w: Optional[float] = Field(None, description="Phoneme width noise (default 0.8)")
    sentence_silence: Optional[float] = Field(None, description="Seconds of silence after each sentence (default 0.2)")
    rate: Optional[float] = Field(None, description="Convenience: multiply length_scale inversely, e.g., 1.05=faster, 0.95=slower")
    volume: Optional[float] = Field(None, description="Post gain multiplier on PCM frames (e.g., 1.2 = +20%)")

# -------- App --------
app = FastAPI(title="Piper TTS Service", version="1.0")

# Ensure ESPEAK_DATA_PATH for Piper
os.environ.setdefault("ESPEAK_DATA_PATH", ESPEAK_DATA_PATH)

# Lazy-import Piper only once FastAPI spins up
@lru_cache(maxsize=1)
def _piper_lib():
    import piper  # type: ignore
    return piper

# Discover available models from directory
def _discover_models() -> Dict[str, str]:
    """Scan PIPER_MODELS_DIR for .onnx files and return voice_name -> model_path mapping"""
    models = {}
    if not os.path.exists(PIPER_MODELS_DIR):
        print(f"[WARN] Models directory not found: {PIPER_MODELS_DIR}")
        return models
    
    try:
        for filename in os.listdir(PIPER_MODELS_DIR):
            if filename.endswith('.onnx'):
                model_path = os.path.join(PIPER_MODELS_DIR, filename)
                config_path = model_path + '.json'
                
                # Only include models that have corresponding config files
                if os.path.exists(config_path):
                    # Use filename without extension as voice name
                    voice_name = filename[:-5]  # Remove .onnx
                    models[voice_name] = model_path
                else:
                    print(f"[WARN] Missing config file for {filename}, skipping")
    except Exception as e:
        print(f"[ERROR] Failed to scan models directory: {e}")
    
    return models

VOICES: Dict[str, str] = _discover_models()

if not VOICES:
    print(f"[WARN] No models found in {PIPER_MODELS_DIR}. Ensure .onnx files have corresponding .json configs.")
else:
    print(f"[INFO] Discovered {len(VOICES)} voice models: {list(VOICES.keys())}")

# Cache of loaded PiperVoice objects
_loaded_voices: Dict[str, object] = {}

def _load_voice(name: str):
    if name in _loaded_voices:
        return _loaded_voices[name]
    piper = _piper_lib()
    model_path = VOICES.get(name)
    if not model_path:
        raise HTTPException(status_code=404, detail=f"Voice '{name}' not found")
    config_path = model_path + ".json" if os.path.exists(model_path + ".json") else None
    if config_path is None:
        # Some distros store config alongside with different naming; fail clearly
        raise HTTPException(status_code=400, detail=f"Config JSON not found for model: {model_path}. Expected {model_path}.json")
    voice = piper.PiperVoice.load(model_path, config_path)  # loads and warms the model
    _loaded_voices[name] = voice
    return voice

def _get_sample_rate(voice) -> int:
    # PiperVoice usually exposes sample rate via attribute or config; try both
    for attr in ("sample_rate_hz", "sample_rate"):
        sr = getattr(voice, attr, None)
        if isinstance(sr, int) and sr > 0:
            return sr
    # last resort: 22050 (typical for many voices)
    return 22050

def _apply_post_gain(pcm_bytes: bytes, volume: Optional[float]) -> bytes:
    if not volume or abs(volume - 1.0) < 1e-6:
        return pcm_bytes
    import array
    # 16-bit signed PCM
    a = array.array("h")
    a.frombytes(pcm_bytes)
    gain = float(volume)
    for i in range(len(a)):
        v = int(a[i] * gain)
        if v > 32767: v = 32767
        if v < -32768: v = -32768
        a[i] = v
    return a.tobytes()

@app.get("/health")
def health():
    return {"status": "ok", "voices": list(VOICES.keys()), "models_dir": PIPER_MODELS_DIR, "espeak_data": os.environ.get("ESPEAK_DATA_PATH")}

@app.get("/voices")
def voices():
    return VOICES

@app.post("/synthesize/{voice_name}")
def synth(voice_name: str, req: SynthesisRequest = Body(...)):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")
    
    # Check if voice exists
    if voice_name not in VOICES:
        raise HTTPException(status_code=404, detail=f"Voice '{voice_name}' not found. Available voices: {list(VOICES.keys())}")

    voice = _load_voice(voice_name)
    sr = _get_sample_rate(voice)

    # Convert "rate" to Piper length_scale if provided:
    # Higher rate -> faster speech -> smaller length_scale
    length_scale = req.length_scale
    if req.rate and not length_scale:
        # simple mapping: length_scale = 1 / rate
        try:
            length_scale = 1.0 / float(req.rate)
        except Exception:
            pass

    # Build synthesis config from request parameters
    import piper
    syn_config = None
    if any([req.speaker is not None, req.noise_scale is not None, length_scale is not None, 
            req.noise_w is not None, req.sentence_silence is not None]):
        syn_config = piper.SynthesisConfig()
        if req.speaker is not None:          syn_config.speaker_id = req.speaker
        if req.noise_scale is not None:      syn_config.noise_scale = float(req.noise_scale)
        if length_scale is not None:         syn_config.length_scale = float(length_scale)
        if req.noise_w is not None:          syn_config.noise_w = float(req.noise_w)
        if req.sentence_silence is not None: syn_config.sentence_silence = float(req.sentence_silence)

    # Synthesize audio chunks and build WAV
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)      # 16-bit signed
        wf.setframerate(sr)
        
        # Synthesize returns AudioChunk objects with audio data
        for chunk in voice.synthesize(req.text, syn_config):
            audio_data = chunk.audio_int16_bytes  # Get the raw 16-bit PCM bytes
            if req.volume and abs(req.volume - 1.0) > 1e-6:
                audio_data = _apply_post_gain(audio_data, req.volume)
            wf.writeframes(audio_data)

    audio_bytes = buf.getvalue()
    return Response(content=audio_bytes, media_type="audio/wav")
