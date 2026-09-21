# GPL Tracker - Dockerfile
FROM python:3.12-slim

WORKDIR /app

# Configure Python environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/app/data \
    SERVER_HOST=0.0.0.0 \
    SERVER_PORT=8000

# Install curl for container health check
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY gpl_tracker/ ./gpl_tracker/
COPY app.py .
COPY README.md .

# Ensure persistent data directory exists
RUN mkdir -p /app/data

# Persistent storage volume for SQLite database
VOLUME ["/app/data"]

# Expose HTTP port
EXPOSE 8000

# Container healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/vehicle || exit 1

# Start server (with --no-browser flag for headless server environment)
CMD ["python", "app.py", "--no-browser"]

