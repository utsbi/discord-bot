FROM python:3.12-slim

# Runtime environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# System dependencies:
#   - ffmpeg:   audio mixing in ai/transcription.py + discord voice playback/recording
#   - libopus0: Opus codec required by py-cord for voice send/receive
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg libopus0 \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

# Install dependencies first for better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY steve/ steve/

# Run as a non-root user; ensure the log directory is writable by it.
# logs/ is mounted as a volume in docker-compose for persistence.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/logs \
    && chown -R appuser:appuser /app
USER appuser

CMD ["uv", "run", "--no-dev", "python", "steve/main.py"]
