# EDA Hardware Optimization OpenEnv — Docker Build
# Multi-stage build with EDA tools installed inside the container

ARG BASE_IMAGE=ghcr.io/meta-pytorch/openenv-base:latest
FROM ${BASE_IMAGE} AS builder

WORKDIR /app

# Install system dependencies including EDA tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        iverilog \
        yosys \
        patch \
        && rm -rf /var/lib/apt/lists/*

# Build args
ARG BUILD_MODE=in-repo
ARG ENV_NAME=verilog_env

# Copy environment code
COPY . /app/env

WORKDIR /app/env

# Install uv if missing
RUN if ! command -v uv >/dev/null 2>&1; then \
        curl -LsSf https://astral.sh/uv/install.sh | sh && \
        mv /root/.local/bin/uv /usr/local/bin/uv && \
        mv /root/.local/bin/uvx /usr/local/bin/uvx; \
    fi

# Install Python dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-install-project --no-editable; \
    else \
        uv sync --no-install-project --no-editable; \
    fi

RUN --mount=type=cache,target=/root/.cache/uv \
    if [ -f uv.lock ]; then \
        uv sync --frozen --no-editable; \
    else \
        uv sync --no-editable; \
    fi

# Final runtime stage
FROM ${BASE_IMAGE}

WORKDIR /app

# Install runtime EDA tools
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git \
        iverilog \
        yosys \
        patch \
        && rm -rf /var/lib/apt/lists/*

# Validate EDA tools are available
RUN iverilog -V 2>&1 | head -1 && \
    yosys -V 2>&1 | head -1 && \
    git --version

# Copy virtual environment from builder
COPY --from=builder /app/env/.venv /app/.venv

# Copy environment code
COPY --from=builder /app/env /app/env

# Set PATH to use the virtual environment
ENV PATH="/app/.venv/bin:$PATH"

# Set PYTHONPATH so imports work correctly
ENV PYTHONPATH="/app/env:$PYTHONPATH"

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Expose port
EXPOSE 8000

# Run the FastAPI server
CMD ["sh", "-c", "cd /app/env && uvicorn server.app:app --host 0.0.0.0 --port 8000"]
