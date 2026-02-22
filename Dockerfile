# BrightDayBot Docker Image
# Based on https://docs.astral.sh/uv/guides/integration/docker/

FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# uv build optimizations
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_NO_DEV=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies (cached layer — only rebuilds when deps change)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Set PATH so venv and playwright CLI are available
ENV PATH="/app/.venv/bin:$PATH"

# Install Playwright system dependencies (as root)
RUN playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --system --gid 999 nonroot \
    && useradd --system --gid 999 --uid 999 --create-home nonroot

# Copy application code (owned by nonroot)
COPY --chown=nonroot:nonroot . /app

# Create data directories
RUN mkdir -p data/logs data/storage data/tracking data/backups data/cache \
    && chown -R nonroot:nonroot data

# Switch to non-root user
USER nonroot

# Install Playwright browser binary (as non-root user)
RUN playwright install chromium

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from utils.health import get_system_status; import sys; sys.exit(0 if get_system_status()['overall'] == 'ok' else 1)"

# Default command
CMD ["uv", "run", "python", "app.py"]
