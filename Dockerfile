# Use a Python Alpine base image
FROM python:3.13-alpine

# Build arguments for dynamic labels from the GitHub Actions workflow
ARG BUILD_DATE
ARG VCS_REF
ARG VERSION
ARG IMAGE_TITLE="nhmesh/producer"
ARG IMAGE_DESCRIPTION="A Docker container that connects to a Meshtastic node and publishes packets to an MQTT broker"
ARG GITHUB_REPO="nhmesh/nhmesh-producer"

# OCI annotations - https://github.com/opencontainers/image-spec/blob/main/annotations.md
LABEL org.opencontainers.image.title="${IMAGE_TITLE}"
LABEL org.opencontainers.image.description="${IMAGE_DESCRIPTION}"
LABEL org.opencontainers.image.url="https://github.com/${GITHUB_REPO}"
LABEL org.opencontainers.image.source="https://github.com/${GITHUB_REPO}"
LABEL org.opencontainers.image.version="${VERSION}"
LABEL org.opencontainers.image.created="${BUILD_DATE}"
LABEL org.opencontainers.image.revision="${VCS_REF}"
LABEL org.opencontainers.image.documentation="https://github.com/${GITHUB_REPO}/blob/${VCS_REF}/README.md"

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apk add --no-cache \
    gcc \
    musl-dev \
    python3-dev \
    libffi-dev \
    openssl-dev

# Install poetry
RUN pip install --no-cache-dir poetry

# Copy only dependency files to leverage Docker cache
COPY pyproject.toml poetry.lock* /app/

# Configure poetry and install dependencies (production only)
RUN poetry config virtualenvs.create false && \
    poetry install --no-interaction --no-ansi --no-root --only=main

# Now copy the application code
COPY ./nhmesh_producer /app/nhmesh_producer

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Command to run the application as a module
CMD ["python", "-m", "nhmesh_producer.producer"]
