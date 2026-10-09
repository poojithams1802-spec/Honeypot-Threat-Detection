FROM python:3.12-slim

# Install attack tooling
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        openssh-client \
        sshpass \
        nmap \
        hydra \
        netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Install Python attack library
RUN pip install --no-cache-dir paramiko

WORKDIR /attacks
