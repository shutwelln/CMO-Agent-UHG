FROM python:3.11-slim AS base

# System deps for aiosqlite, Pillow, and Node.js (Remotion)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

# Copy application source
COPY src/ src/
COPY data/brand_voices/_example.txt data/brand_voices/_example.txt
COPY data/fonts/ data/fonts/
COPY .env.template .env.template

# Create data directories
RUN mkdir -p data/brand_voices data/memory data/experiments \
    data/analytics data/editorial data/videos data/motion_graphics \
    data/compositions data/decks

# Default port for web UI
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import cmo_agent; print('ok')" || exit 1

# Default: start web UI
CMD ["cmo", "serve", "--host", "0.0.0.0", "--port", "8000"]
