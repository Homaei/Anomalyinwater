FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libgl1-mesa-glx \
    libgl1-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Create directories
RUN mkdir -p /app/models /app/uploads /app/logs

# Create non-root user
RUN useradd --create-home --shell /bin/bash ml_user && \
    chown -R ml_user:ml_user /app

USER ml_user

# Environment variables
ENV PYTHONPATH=/app

# Health check (CPU version)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import torch; print('ML Worker healthy')" || exit 1

# Run the ML worker
CMD ["python", "app/main.py"]
