FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port (Railway/Render auto-detect, but explicit is good)
ENV PORT=8080
EXPOSE 8080

# Use gunicorn with gevent workers for SSE support
CMD gunicorn --bind 0.0.0.0:$PORT --workers 2 --worker-class gevent --timeout 120 --keep-alive 5 server:app
