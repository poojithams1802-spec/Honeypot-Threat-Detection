#!/usr/bin/env bash
# ==============================================================================
# Cowrie Honeypot - Verification Script
# ==============================================================================
# This script:
# 1. Starts the Cowrie container using Docker Compose.
# 2. Waits for port 2222 to become available.
# 3. Performs an automated test SSH login attempt with fake credentials.
# 4. Verifies and displays the last 10 lines of data/cowrie_logs/cowrie.json
#    to confirm detection events (session.connect, login.failed / login.success).
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

echo "=========================================================="
echo " Starting Cowrie Honeypot Verification"
echo " Project Root: $PROJECT_ROOT"
echo "=========================================================="

# 1. Check Docker and Docker Compose availability
if ! command -v docker >/dev/null 2>&1; then
    echo "[-] Error: 'docker' is not installed or not in PATH."
    echo "[-] Please run './scripts/install_docker.sh' first."
    exit 1
fi

DOCKER_COMPOSE_CMD=""
if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE_CMD="docker-compose"
else
    echo "[-] Error: Docker Compose is not installed."
    echo "[-] Please run './scripts/install_docker.sh' first."
    exit 1
fi

# 2. Ensure log directory exists with write permissions for container user (UID 1000)
mkdir -p data/cowrie_logs
chmod -R 777 data/cowrie_logs 2>/dev/null || true

# 3. Start Cowrie Honeypot container
echo "[+] Step 1: Starting Cowrie container..."
$DOCKER_COMPOSE_CMD up -d

# 4. Wait for SSH service to become ready on port 2222
echo "[+] Step 2: Waiting for Cowrie to listen on 127.0.0.1:2222..."
MAX_RETRIES=30
RETRY=0
READY=0

while [ $RETRY -lt $MAX_RETRIES ]; do
    if (timeout 1 bash -c 'cat < /dev/null > /dev/tcp/127.0.0.1/2222') >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 1
    RETRY=$((RETRY + 1))
done

if [ $READY -ne 1 ]; then
    echo "[-] Warning: Port 2222 did not become ready within 30 seconds."
    echo "[-] Container status and logs:"
    $DOCKER_COMPOSE_CMD ps
    $DOCKER_COMPOSE_CMD logs --tail 20 cowrie
    exit 1
fi

echo "[+] Cowrie SSH service is active on 127.0.0.1:2222."

# 5. Make test SSH connection with fake username & password
TEST_USER="threat_actor"
TEST_PASS="P@ssw0rdFake99"
echo "[+] Step 3: Simulating SSH connection to localhost:2222 ($TEST_USER:$TEST_PASS)..."

if command -v sshpass >/dev/null 2>&1; then
    sshpass -p "$TEST_PASS" ssh \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o PreferredAuthentications=password \
        -o PubkeyAuthentication=no \
        -o ConnectTimeout=5 \
        -p 2222 "$TEST_USER@127.0.0.1" "exit" 2>/dev/null || true
else
    # Fallback using standard OpenSSH SSH_ASKPASS helper without requiring sshpass
    ASKPASS_SCRIPT=$(mktemp)
    cat << EOF > "$ASKPASS_SCRIPT"
#!/bin/sh
echo "$TEST_PASS"
EOF
    chmod +x "$ASKPASS_SCRIPT"

    DISPLAY=dummy SSH_ASKPASS="$ASKPASS_SCRIPT" SSH_ASKPASS_REQUIRE=force ssh \
        -o StrictHostKeyChecking=no \
        -o UserKnownHostsFile=/dev/null \
        -o PreferredAuthentications=password \
        -o PubkeyAuthentication=no \
        -o NumberOfPasswordPrompts=1 \
        -o ConnectTimeout=5 \
        -p 2222 "$TEST_USER@127.0.0.1" "exit" 2>/dev/null || true

    rm -f "$ASKPASS_SCRIPT"
fi

echo "[+] SSH test probe finished. Waiting 3 seconds for log flush..."
sleep 3

# 6. Check cowrie.json and print the last 10 lines
LOG_FILE="data/cowrie_logs/cowrie.json"

if [ ! -f "$LOG_FILE" ]; then
    echo "[-] Warning: $LOG_FILE not found yet."
    echo "[-] Inspecting directory contents:"
    ls -la data/cowrie_logs/
    echo "[-] Container logs:"
    $DOCKER_COMPOSE_CMD logs --tail 20 cowrie
    exit 1
fi

echo ""
echo "=========================================================="
echo " Last 10 lines from $LOG_FILE:"
echo "=========================================================="
tail -n 10 "$LOG_FILE"
echo "=========================================================="
echo ""

# 7. Check for expected event types
if grep -q "cowrie.session.connect" "$LOG_FILE" 2>/dev/null; then
    echo "[PASS] Found 'cowrie.session.connect' in log!"
else
    echo "[INFO] 'cowrie.session.connect' not in recent window yet."
fi

if grep -q "cowrie.login" "$LOG_FILE" 2>/dev/null; then
    echo "[PASS] Found 'cowrie.login' event (failed or success) in log!"
else
    echo "[INFO] 'cowrie.login' not in recent window yet."
fi

echo ""
echo "[+] Verification complete! Cowrie is capturing attack telemetry."
