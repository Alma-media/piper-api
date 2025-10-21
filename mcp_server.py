#!/usr/bin/env python3
"""
MCP Server for Piper TTS API

This module provides MCP (Model Context Protocol) server functionality for the Piper TTS service.
It exposes text-to-speech capabilities as MCP tools that can be used by MCP-compatible clients.
"""

import asyncio
import base64
import io
import json
import os
import tempfile
import wave
from typing import Any, Dict, List, Optional, Sequence

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequest,
    CallToolResult,
    ListToolsRequest,
    TextContent,
    Tool,
)
from pydantic import AnyUrl

# Import the existing Piper functionality
from main import (
    VOICES,
    _load_voice,
    _get_sample_rate,
    _apply_post_gain,
    SynthesisRequest,
)

# MCP Server instance
server = Server("piper-tts")


@server.list_tools()
async def handle_list_tools() -> List[Tool]:
    """List available TTS tools."""
    tools = [
        Tool(
            name="text_to_speech",
            description="Convert text to speech using Piper TTS. Returns base64-encoded WAV audio.",
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "The text to convert to speech"
                    },
                    "voice": {
                        "type": "string",
                        "description": f"Voice to use for synthesis. Available voices: {', '.join(VOICES.keys())}",
                        "enum": list(VOICES.keys()) if VOICES else ["no-voices-available"]
                    },
                    "speaker": {
                        "type": "integer",
                        "description": "Multi-speaker index (if model supports)",
                        "minimum": 0
                    },
                    "rate": {
                        "type": "number",
                        "description": "Speech rate multiplier (e.g., 1.05 = faster, 0.95 = slower)",
                        "minimum": 0.1,
                        "maximum": 3.0
                    },
                    "volume": {
                        "type": "number",
                        "description": "Volume multiplier (e.g., 1.2 = +20% louder)",
                        "minimum": 0.1,
                        "maximum": 3.0
                    },
                    "noise_scale": {
                        "type": "number",
                        "description": "Generator noise scale (default 0.667)",
                        "minimum": 0.0,
                        "maximum": 2.0
                    },
                    "length_scale": {
                        "type": "number",
                        "description": "Phoneme length scale (default 1.0)",
                        "minimum": 0.1,
                        "maximum": 3.0
                    },
                    "noise_w": {
                        "type": "number",
                        "description": "Phoneme width noise (default 0.8)",
                        "minimum": 0.0,
                        "maximum": 2.0
                    },
                    "sentence_silence": {
                        "type": "number",
                        "description": "Seconds of silence after each sentence (default 0.2)",
                        "minimum": 0.0,
                        "maximum": 5.0
                    }
                },
                "required": ["text", "voice"]
            }
        ),
        Tool(
            name="list_voices",
            description="List all available TTS voices and their model paths.",
            inputSchema={
                "type": "object",
                "properties": {},
                "additionalProperties": False
            }
        ),
        Tool(
            name="get_voice_info",
            description="Get detailed information about a specific voice.",
            inputSchema={
                "type": "object",
                "properties": {
                    "voice": {
                        "type": "string",
                        "description": "Voice name to get information about",
                        "enum": list(VOICES.keys()) if VOICES else ["no-voices-available"]
                    }
                },
                "required": ["voice"]
            }
        )
    ]
    
    return tools


@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle tool calls."""
    
    if name == "text_to_speech":
        return await _handle_text_to_speech(arguments)
    elif name == "list_voices":
        return await _handle_list_voices(arguments)
    elif name == "get_voice_info":
        return await _handle_get_voice_info(arguments)
    else:
        raise ValueError(f"Unknown tool: {name}")


async def _handle_text_to_speech(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle text-to-speech conversion."""
    try:
        text = arguments.get("text", "").strip()
        voice_name = arguments.get("voice")
        
        if not text:
            raise ValueError("Text cannot be empty")
        
        if not voice_name:
            raise ValueError("Voice must be specified")
        
        if voice_name not in VOICES:
            available_voices = ", ".join(VOICES.keys())
            raise ValueError(f"Voice '{voice_name}' not found. Available voices: {available_voices}")
        
        # Create synthesis request
        req = SynthesisRequest(
            text=text,
            speaker=arguments.get("speaker"),
            noise_scale=arguments.get("noise_scale"),
            length_scale=arguments.get("length_scale"),
            noise_w=arguments.get("noise_w"),
            sentence_silence=arguments.get("sentence_silence"),
            rate=arguments.get("rate"),
            volume=arguments.get("volume")
        )
        
        # Load voice and get sample rate
        voice = _load_voice(voice_name)
        sr = _get_sample_rate(voice)
        
        # Handle rate conversion to length_scale
        length_scale = req.length_scale
        if req.rate and not length_scale:
            try:
                length_scale = 1.0 / float(req.rate)
            except Exception:
                pass
        
        # Build synthesis config
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
        
        # Synthesize audio
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit signed
            wf.setframerate(sr)
            
            for chunk in voice.synthesize(req.text, syn_config):
                audio_data = chunk.audio_int16_bytes
                if req.volume and abs(req.volume - 1.0) > 1e-6:
                    audio_data = _apply_post_gain(audio_data, req.volume)
                wf.writeframes(audio_data)
        
        audio_bytes = buf.getvalue()
        
        # Encode audio as base64
        audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        
        return [
            TextContent(
                type="text",
                text=f"Successfully synthesized speech for text: '{text[:50]}{'...' if len(text) > 50 else ''}'\n"
                     f"Voice: {voice_name}\n"
                     f"Audio format: WAV, 16-bit, {sr}Hz, mono\n"
                     f"Audio size: {len(audio_bytes)} bytes\n"
                     f"Base64 encoded audio:\n{audio_b64}"
            )
        ]
        
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error during text-to-speech synthesis: {str(e)}"
            )
        ]


async def _handle_list_voices(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle listing available voices."""
    try:
        if not VOICES:
            return [
                TextContent(
                    type="text",
                    text="No voices are currently available. Please check your PIPER_MODELS_DIR configuration."
                )
            ]
        
        voice_info = []
        for voice_name, model_path in VOICES.items():
            config_path = model_path + ".json"
            config_info = "No config info available"
            
            if os.path.exists(config_path):
                try:
                    with open(config_path, 'r') as f:
                        config = json.load(f)
                        language = config.get('language', 'unknown')
                        dataset = config.get('dataset', 'unknown')
                        config_info = f"Language: {language}, Dataset: {dataset}"
                except Exception:
                    config_info = "Config file exists but couldn't be read"
            
            voice_info.append(f"• **{voice_name}**: {model_path}\n  {config_info}")
        
        return [
            TextContent(
                type="text",
                text=f"Available TTS voices ({len(VOICES)} total):\n\n" + "\n\n".join(voice_info)
            )
        ]
        
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error listing voices: {str(e)}"
            )
        ]


async def _handle_get_voice_info(arguments: Dict[str, Any]) -> List[TextContent]:
    """Handle getting information about a specific voice."""
    try:
        voice_name = arguments.get("voice")
        
        if not voice_name:
            raise ValueError("Voice name must be specified")
        
        if voice_name not in VOICES:
            available_voices = ", ".join(VOICES.keys())
            raise ValueError(f"Voice '{voice_name}' not found. Available voices: {available_voices}")
        
        model_path = VOICES[voice_name]
        config_path = model_path + ".json"
        
        info = [f"**Voice**: {voice_name}", f"**Model Path**: {model_path}"]
        
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                info.extend([
                    f"**Language**: {config.get('language', 'unknown')}",
                    f"**Dataset**: {config.get('dataset', 'unknown')}",
                    f"**Sample Rate**: {config.get('audio', {}).get('sample_rate', 'unknown')} Hz",
                    f"**Phoneme Type**: {config.get('phoneme_type', 'unknown')}",
                ])
                
                # Add speaker info if available
                num_speakers = config.get('num_speakers')
                if num_speakers and num_speakers > 1:
                    info.append(f"**Multi-speaker**: Yes ({num_speakers} speakers)")
                else:
                    info.append("**Multi-speaker**: No")
                
                # Add additional config details
                if 'espeak' in config:
                    info.append(f"**eSpeak Voice**: {config['espeak'].get('voice', 'unknown')}")
                
            except Exception as e:
                info.append(f"**Config Error**: Could not read config file: {str(e)}")
        else:
            info.append("**Config**: No config file found")
        
        return [
            TextContent(
                type="text",
                text="\n".join(info)
            )
        ]
        
    except Exception as e:
        return [
            TextContent(
                type="text",
                text=f"Error getting voice info: {str(e)}"
            )
        ]


async def main():
    """Main entry point for the MCP server."""
    # Initialize the server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="piper-tts",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())
