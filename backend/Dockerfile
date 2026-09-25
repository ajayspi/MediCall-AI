# Root-context Dockerfile (G6-Q10 Q2=A1): builds from the REPO ROOT so docker
# compose (docker-compose.yml build.context: .) and Railway (root build
# context) work from ONE file. COPY paths are root-relative; the root
# .dockerignore keeps node_modules/.git/.next/.venv out of the build context.
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./

# Create non-root user
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]