FROM python:3.13-slim

# Set working directory
WORKDIR /opt/ss-confirm

# Create log and download directories
RUN mkdir -p /var/log/ss-confirm /opt/ss-confirm/downloads

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright and Chromium
RUN python -m playwright install chromium

# Copy application code
COPY ss_confirm.py .
COPY README.md .
COPY .env.example .env.example

# Copy credentials (optional, can be mounted as volume)
# Note: credentials.json must exist at build time or be mounted as volume at runtime

# Health check
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "import os; print('OK') if os.path.exists('.') else exit(1)"

# Run the application
CMD ["python", "ss_confirm.py", "--continuous"]
