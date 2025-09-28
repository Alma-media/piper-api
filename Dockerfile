FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    espeak-ng \
    espeak-ng-data \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml ./

# Install Python dependencies
RUN pip install uv && \
    uv pip install --system -r pyproject.toml

# Copy application code
COPY main.py ./

# Create models directory
RUN mkdir -p /app/models

# Set environment variables
ENV PIPER_MODELS_DIR=/app/models
ENV ESPEAK_DATA_PATH=/usr/share/espeak-ng-data

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
