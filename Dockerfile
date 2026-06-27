# Python 3.10 slim as the base image
FROM python:3.10-slim

# Install system dependencies, Node.js, and Chromium with its dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gnupg \
    ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y \
    nodejs \
    chromium \
    libnss3 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxext6 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set Puppeteer to use the installed Chromium inside the container
ENV PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
ENV PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

# Set working directory
WORKDIR /app

# Copy dependency files
COPY package.json package-lock.json* requirements.txt ./

# Install python requirements and node packages
RUN pip install --no-cache-dir -r requirements.txt \
    && npm install

# Copy the rest of the application files
COPY . .

# Expose the API port
EXPOSE 8000

# Start the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
