FROM python:3.12-slim

# DuckDB wheels are precompiled; no build-essential, gcc, or system libs needed for duckdb or other pure-Python deps
WORKDIR /app

# Create non-root user for security
RUN useradd -m -u 1000 app && chown -R app:app /app

# Install requirements with pip cache disabled to reduce image size
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY ./app ./app

# Switch to non-root user
USER app

EXPOSE 8080

# Default command: run uvicorn with 2 workers for modest concurrency
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/').read()" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
