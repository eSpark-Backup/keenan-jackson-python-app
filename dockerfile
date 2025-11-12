# ============================================================
# Board Operations Agent - Square Trivia
# FastAPI + Prometheus + JWT + Reach Mode (Production Build)
# ============================================================

# Base Image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_HOME=/app \
    PORT=8080 \
    DECISION_CYCLE_HOURS=2

# Set working directory
WORKDIR $APP_HOME

# Copy dependency list
COPY requirements.txt .

# Install system dependencies and Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential curl && \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy application source code
COPY . .

# Expose API port
EXPOSE 8080

# Healthcheck (optional but recommended)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s CMD curl -f http://localhost:8080/health || exit 1

# Start the FastAPI app using Uvicorn
CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
