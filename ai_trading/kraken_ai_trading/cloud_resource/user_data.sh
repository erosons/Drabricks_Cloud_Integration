#!/bin/bash
# Bootstrap script for Amazon Linux 2023 — runs once at first boot
set -euo pipefail
exec > >(tee /var/log/kraken-bootstrap.log) 2>&1

echo "=== Kraken Bot Bootstrap: $(date) ==="

# ── System packages ──────────────────────────────────────────────────────────
dnf update -y
dnf install -y \
  python3.11 python3.11-pip \
  git rsync tmux htop \
  docker \
  amazon-cloudwatch-agent

# Enable Docker for Prometheus + Grafana via docker-compose
systemctl enable --now docker

# Install docker-compose v2
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-x86_64" \
  -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# ── App user + directories ───────────────────────────────────────────────────
useradd -r -m -s /bin/bash -d /opt/kraken_bot kraken 2>/dev/null || true
usermod -aG docker kraken

mkdir -p /opt/kraken_bot/{logs,pairs,src,monitoring}
chown -R kraken:kraken /opt/kraken_bot

# ── Python virtual environment ───────────────────────────────────────────────
python3.11 -m venv /opt/kraken_bot/venv
/opt/kraken_bot/venv/bin/pip install --upgrade pip setuptools wheel

# ── Systemd service: trading bot ────────────────────────────────────────────
cat > /etc/systemd/system/kraken-bot.service << 'SERVICE'
[Unit]
Description=Kraken AI Trading Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=kraken
WorkingDirectory=/opt/kraken_bot
EnvironmentFile=/opt/kraken_bot/.env
ExecStart=/opt/kraken_bot/venv/bin/python launcher.py
Restart=on-failure
RestartSec=15
StandardOutput=journal
StandardError=journal
# Raise open-file limit for many WebSocket connections
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
SERVICE

systemctl daemon-reload
# Service starts after deploy.sh pushes code + .env

# ── CloudWatch agent basic config ────────────────────────────────────────────
mkdir -p /opt/aws/amazon-cloudwatch-agent/etc
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json << 'CW'
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/kraken-bootstrap.log",
            "log_group_name": "/kraken-bot/bootstrap",
            "log_stream_name": "{instance_id}"
          }
        ]
      }
    }
  }
}
CW

/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config -m ec2 \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json \
  -s || true

echo "=== Bootstrap complete: $(date) ==="
