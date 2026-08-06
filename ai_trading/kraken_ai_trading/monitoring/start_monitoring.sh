#!/usr/bin/env bash
# Start Prometheus + Grafana for the Kraken trading bot dashboard.
# Run from any directory. Ctrl-C kills both.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROM_DATA="${SCRIPT_DIR}/prometheus_data"
GF_PROV="${SCRIPT_DIR}/grafana/provisioning"
GF_DASH="${SCRIPT_DIR}/grafana/dashboards"

mkdir -p "$PROM_DATA"

# ── Prometheus ──────────────────────────────────────────────────────────
echo "[monitor] Starting Prometheus on :9090 ..."
prometheus \
  --config.file="${SCRIPT_DIR}/prometheus.yml" \
  --storage.tsdb.path="${PROM_DATA}" \
  --web.listen-address="0.0.0.0:9090" \
  --log.level=warn \
  &
PROM_PID=$!

# ── Grafana ─────────────────────────────────────────────────────────────
echo "[monitor] Starting Grafana on :3000 ..."
GF_PATHS_PROVISIONING="$GF_PROV" \
GF_PATHS_LOGS="/var/log/grafana" \
GF_PATHS_DATA="/var/lib/grafana" \
GF_AUTH_ANONYMOUS_ENABLED=true \
GF_AUTH_ANONYMOUS_ORG_NAME="Main Org." \
GF_SECURITY_ADMIN_PASSWORD=admin \
GF_SERVER_HTTP_PORT=3000 \
  grafana server \
    --homepath /usr/share/grafana \
    cfg:paths.provisioning="$GF_PROV" \
    cfg:paths.logs="/var/log/grafana" \
    cfg:paths.data="/var/lib/grafana" \
  &>/tmp/grafana_bot.log &
GRAFANA_PID=$!

# Wait for Grafana health
echo -n "[monitor] Waiting for Grafana"
for i in $(seq 1 30); do
  sleep 1
  if curl -s http://localhost:3000/api/health 2>/dev/null | grep -q '"database":"ok"'; then
    echo " ready!"
    break
  fi
  echo -n "."
done

echo ""
echo "────────────────────────────────────────────────────────"
echo " Dashboard  →  http://localhost:3000"
echo "             login: admin / admin"
echo " Metrics    →  http://localhost:9090"
echo " Bot feeds  →  :8001 (XRP)  :8002 (ETH)  :8003 (DOGE)"
echo "────────────────────────────────────────────────────────"
echo "[monitor] Prometheus=$PROM_PID  Grafana=$GRAFANA_PID"
echo "[monitor] Ctrl-C to stop both."

trap "echo; echo '[monitor] Stopping...'; kill $PROM_PID $GRAFANA_PID 2>/dev/null; exit 0" INT TERM

wait $PROM_PID $GRAFANA_PID
