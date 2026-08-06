# Kraken AI Trading Bot — Action Changelog

## 2026-06-11
- [INFRA] Started EC2 instance i-0cb133a2b500dcc23 (m5n.large) at 54.167.228.52 — was stopped
- [DEPLOY] Ran cloud_resource/deploy.sh — synced all project files to /opt/kraken_bot on EC2
- [BOT] kraken-bot.service restarted and confirmed active (running) — all pairs staggered startup
- [MONITORING] Grafana, Prometheus, Loki, Promtail, node-exporter confirmed running via docker-compose

## 2026-06-25
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no -o ConnectTimeout=10 ec2-user@54.167.228.52 "echo '=== SERVER ONLINE ===' && uptime && echo '' && echo '=== BOT PROCESSES ===' && ps aux | grep main.py | grep -v grep && echo '' && echo '=== LAUNCHER STATUS ===' && ps aux | grep launcher.py | grep -v grep && echo '' && echo '=== SYSTEMD SERVICES ===' && sudo systemctl status kraken-bot --no-pager 2>/dev/null || echo 'no kraken-bot service' && echo '' && echo '=== DISK & MEMORY ===' && df -h / && free -h"

## 2026-06-25
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "for pair in akt ethfi crv dash jto; do echo \"=== \$pair ===\"; grep -i 'take_profit\|tp\|profit' /opt/kraken_bot/pairs/\$pair.env 2>/dev/null || echo 'not in env'; done"

## 2026-06-25
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "tail -200 /opt/kraken_bot/logs/ethfi.log | grep -E 'ENTRY|EXIT|BUY|SELL|FILL|entry|exit|cost|profit|pnl|PNL|position|POSITION|ORDER|order' | tail -50"

## 2026-06-25
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "grep -ri 'fee' /opt/kraken_bot/pairs/ethfi.env /opt/kraken_bot/.env 2>/dev/null; echo '---SRC---'; grep -ri 'fee_rate\|TAKER\|MAKER\|FEE_PCT' /opt/kraken_bot/src/ 2>/dev/null | head -20"
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "grep -ri 'KRAKEN_FEE\|fee_rate\|taker_fee\|maker_fee\|0\.16\|0\.26\|0\.002\|0\.001' /opt/kraken_bot/ --include='*.py' --include='*.env' 2>/dev/null | head -20"

## 2026-06-26
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "cat /opt/kraken_bot/.env | grep -v 'KEY\|SECRET\|PASSWORD\|TOKEN' | head -30" && echo "===" && ls /workspaces/Drabricks_Cloud_Integration/ai_trading/kraken_ai_trading/src/
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "sudo cat /opt/kraken_bot/.env | grep -v 'KEY\|SECRET\|PASSWORD\|TOKEN' | head -30" && echo "===" && cat /workspaces/Drabricks_Cloud_Integration/ai_trading/kraken_ai_trading/src/client/*.py | grep -E 'class|def |kraken_api|base_url|API_KEY|api_key' | head -30
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] scp -i ~/.ssh/kraken_project.pem \
- [CMD] scp -i ~/.ssh/kraken_project.pem \
- [CMD] scp -i ~/.ssh/kraken_project.pem \
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] sudo journalctl -u kraken-account-exporter -n 20 --no-pager
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "

## 2026-06-26
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] sudo journalctl -u kraken-account-exporter -n 20 --no-pager | grep -E 'ClosedOrders|closed|ERROR|Permission'

## 2026-06-27
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] scp -i ~/.ssh/kraken_project.pem \
- [CMD]   scp -i ~/.ssh/kraken_project.pem \
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] sudo systemctl restart kraken-bot
- [CMD] sudo systemctl status kraken-bot --no-pager | head -15
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "sleep 10 && sudo journalctl -u kraken-bot -n 60 --no-pager | grep 'Risk: ORDER'"
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] sudo systemctl restart kraken-bot
- [CMD] sudo journalctl -u kraken-bot -n 80 --no-pager | grep 'Risk: ORDER' | grep -v '10\.0000'
- [CMD] sudo journalctl -u kraken-bot -n 80 --no-pager | grep 'Risk: ORDER' | head -10
- [CMD] ssh -i ~/.ssh/kraken_project.pem -o StrictHostKeyChecking=no ec2-user@54.167.228.52 "
- [CMD] sudo systemctl restart kraken-bot
- [CMD] sudo journalctl -u kraken-bot -n 100 --no-pager | grep 'Risk: ORDER'

## 2026-06-30
- [CMD] aws ec2 stop-instances --instance-ids i-0cb133a2b500dcc23 --region us-east-1
- [CMD] aws ec2 wait instance-stopped --instance-ids i-0cb133a2b500dcc23 --region us-east-1 && echo "stopped"
