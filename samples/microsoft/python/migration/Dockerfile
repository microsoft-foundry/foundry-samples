# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    lsb-release \
    && rm -rf /var/lib/apt/lists/*

# Install Azure CLI
RUN curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies from requirements.txt
RUN pip install -r requirements.txt

# Copy the migration script and supporting files
COPY v1_to_v2_migration.py .
COPY read_cosmos_data.py .

# Create a non-root user for security
RUN useradd -m -u 1000 migration

# Create Azure CLI directory with proper permissions for the migration user
RUN mkdir -p /home/migration/.azure && chown -R migration:migration /home/migration/.azure

# Install gosu for safe user switching (before creating entrypoint)
RUN apt-get update && apt-get install -y gosu && rm -rf /var/lib/apt/lists/*

# Create entrypoint script that runs as root for package installation, then drops to migration user
RUN echo '#!/bin/bash\n\
set -e\n\
if [ "$NEED_BETA_VERSION" = "true" ]; then\n\
    echo "🔧 Installing azure-ai-projects beta version for connection string support..."\n\
    pip install --quiet --upgrade azure-ai-projects==1.0.0b10\n\
    echo "✅ Beta version 1.0.0b10 installed"\n\
else\n\
    echo "✅ Using standard azure-ai-projects version 1.0.0"\n\
fi\n\
echo "🔐 Switching to migration user..."\n\
chown -R migration:migration /app\n\
exec gosu migration python v1_to_v2_migration.py "$@"\n\
' > /app/entrypoint.sh && chmod +x /app/entrypoint.sh

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV AZURE_CONFIG_DIR=/home/migration/.azure

# Default command - entrypoint runs as root for package management, then switches to migration user
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["--help"]