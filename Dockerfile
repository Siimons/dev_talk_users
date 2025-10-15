# -------- Stage 1: Build dependencies --------
FROM python:3.12-slim AS builder

# Install system packages required for building Python packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libffi-dev \
    libmariadb-dev \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy and install Python dependencies into a separate directory
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# -------- Stage 2: Final minimal image --------
FROM python:3.12-slim

# Install only runtime system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmariadb3 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Download service readiness utility
ADD https://raw.githubusercontent.com/vishnubob/wait-for-it/master/wait-for-it.sh /wait-for-it.sh
RUN chmod +x /wait-for-it.sh

# Set working directory
WORKDIR /app

# Copy installed dependencies from the builder stage
COPY --from=builder /root/.local /root/.local

# Copy application source code
COPY . .

# Set environment variables for proper Python execution
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONPATH=/app

# Expose the port used by the application
EXPOSE 8000

# Define the container entrypoint
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
