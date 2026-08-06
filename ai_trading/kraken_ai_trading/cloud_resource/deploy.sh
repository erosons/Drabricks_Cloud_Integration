#!/bin/bash
# Deploy kraken_ai_trading to the EC2 instance.
# Usage: bash cloud_resource/deploy.sh <PUBLIC_IP> <PEM_FILE>
# Run from the kraken_ai_trading project root.
set -euo pipefail

PUBLIC_IP="${1:?Usage: $0 <PUBLIC_IP> <PEM_FILE>}"
PEM_FILE="${2:?Usage: $0 <PUBLIC_IP> <PEM_FILE>}"
REMOTE_USER="ec2-user"
APP_DIR="/opt/kraken_bot"
SSH="ssh -i ${PEM_FILE} -o StrictHostKeyChecking=no ${REMOTE_USER}@${PUBLIC_IP}"
SCP="scp -i ${PEM_FILE} -o StrictHostKeyChecking=no"

# Resolve the project root (parent of cloud_resource/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "${SCRIPT_DIR}")"

echo "=== Deploying kraken_ai_trading to ${PUBLIC_IP} ==="

# ── 1. Wait for SSH to be ready ───────────────────────────────────────────────
echo "Waiting for SSH..."
for i in $(seq 1 30); do
  if $SSH "echo ready" &>/dev/null; then break; fi
  sleep 5
done

# ── 2. Sync project files via temp dir (ec2-user owns /tmp, not /opt) ────────
STAGING="/tmp/kraken_deploy"
echo "Syncing project files to staging area..."
rsync -avz --progress \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='*.pyc' \
  --exclude='*.pyo' \
  --exclude='.env' \
  --exclude='cloud_resource/' \
  --exclude='logs/*.pid' \
  --exclude='monitoring/prometheus_data/' \
  --exclude='monitoring/grafana/provisioning/datasources/' \
  -e "ssh -i ${PEM_FILE} -o StrictHostKeyChecking=no" \
  "${PROJECT_ROOT}/" \
  "${REMOTE_USER}@${PUBLIC_IP}:${STAGING}/"

echo "Moving files to ${APP_DIR}..."
$SSH "sudo mkdir -p ${APP_DIR} && \
      sudo rsync -av ${STAGING}/ ${APP_DIR}/ && \
      rm -rf ${STAGING}"

# ── 3. Copy .env (secrets — handled separately) ───────────────────────────────
if [ -f "${PROJECT_ROOT}/.env" ]; then
  echo "Copying .env..."
  $SCP "${PROJECT_ROOT}/.env" "${REMOTE_USER}@${PUBLIC_IP}:/tmp/.env_kraken"
  $SSH "sudo mv /tmp/.env_kraken ${APP_DIR}/.env && sudo chmod 600 ${APP_DIR}/.env"
else
  echo "WARNING: No .env found at ${PROJECT_ROOT}/.env"
  echo "         Copy it manually: scp -i ${PEM_FILE} .env ${REMOTE_USER}@${PUBLIC_IP}:${APP_DIR}/.env"
fi

# ── 4. Fix ownership ──────────────────────────────────────────────────────────
$SSH "sudo id kraken &>/dev/null && sudo chown -R kraken:kraken ${APP_DIR} || sudo chown -R ec2-user:ec2-user ${APP_DIR}"

# ── 5. Install / update Python dependencies ───────────────────────────────────
echo "Installing Python dependencies..."
$SSH "sudo python3.11 -m venv ${APP_DIR}/venv 2>/dev/null || true && \
      sudo ${APP_DIR}/venv/bin/pip install --upgrade pip --quiet && \
      sudo ${APP_DIR}/venv/bin/pip install aiohttp websockets python-dotenv \
        sortedcontainers anthropic prometheus_client --quiet"

# ── 6. Start / restart the trading bot ───────────────────────────────────────
echo "Starting kraken-bot service..."
$SSH "sudo systemctl enable kraken-bot 2>/dev/null && \
      sudo systemctl restart kraken-bot 2>/dev/null || \
      echo 'systemd service not ready yet - run: sudo systemctl start kraken-bot'"
sleep 3
$SSH "sudo systemctl status kraken-bot --no-pager -l 2>/dev/null || echo 'Service status unavailable'"

# ── 7. Start monitoring stack (Prometheus + Grafana via docker-compose) ───────
MONITORING_DIR="${APP_DIR}/monitoring"
$SSH "test -f ${MONITORING_DIR}/docker-compose.yml && \
  cd ${MONITORING_DIR} && sudo docker-compose up -d --remove-orphans || \
  echo 'No monitoring docker-compose.yml found - skipping'"

echo ""
echo "=== Deployment complete ==="
echo "  SSH:       ssh -i ${PEM_FILE} ${REMOTE_USER}@${PUBLIC_IP}"
echo "  Bot logs:  ssh -i ${PEM_FILE} ${REMOTE_USER}@${PUBLIC_IP} 'sudo journalctl -u kraken-bot -f'"
echo "  Grafana:   http://${PUBLIC_IP}:3000"
echo "  Prometheus: http://${PUBLIC_IP}:9090"
