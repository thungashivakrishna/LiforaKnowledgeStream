FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY apps/ ./apps/
COPY infrastructure/seed/ ./infrastructure/seed/
COPY infrastructure/scripts/ ./infrastructure/scripts/
COPY pyproject.toml .
COPY alembic.ini .
COPY infrastructure/migrations/ ./infrastructure/migrations/

# Set Python path to include src
ENV PYTHONPATH=/app/src

# Default command for API
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
