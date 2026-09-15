FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway/Render auto-detect, but explicit is good)
EXPOSE 8080

# Use gunicorn with gevent workers for SSE support
# PORT env var is set by Railway/Render/Fly.io automatically
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 2 --worker-class gevent --timeout 120 --keep-alive 5 server:app"]
