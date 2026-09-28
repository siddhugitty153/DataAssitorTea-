# Minimal, locked-down Python image for executing LLM-generated code
FROM python:3.12-slim

WORKDIR /sandbox

# Create directories for data input and output
RUN mkdir -p /sandbox/data /sandbox/output

# Install data science libraries
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Create non-root user for security
RUN useradd -m -s /bin/bash sandboxuser && \
    chown -R sandboxuser:sandboxuser /sandbox

USER sandboxuser

# Default entrypoint: run a Python script
ENTRYPOINT ["python"]
