FROM python:3.11-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose port (Fly.io will set PORT env var)
EXPOSE 8080

# Run the app - use shell form to allow env var expansion
CMD uvicorn servery_finder_web:app --host 0.0.0.0 --port ${PORT:-8080}

