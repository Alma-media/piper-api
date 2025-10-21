#!/usr/bin/env python3
"""
Standalone MCP server runner for Piper TTS.

This script runs the Piper TTS service as an MCP server.
Usage: python run_mcp_server.py
"""

import asyncio
import sys
from mcp_server import main

if __name__ == "__main__":
    print("Starting Piper TTS MCP Server...", file=sys.stderr)
    asyncio.run(main())
