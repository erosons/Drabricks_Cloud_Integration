# SSH Access — Kraken Bot EC2

## Connection details

| Field | Value |
|---|---|
| Public IP | `54.167.228.52` (Elastic IP — stable across reboots) |
| User | `ec2-user` |
| Key | `~/.ssh/kraken_project.pem` |
| Instance | `i-0cb133a2b500dcc23` (m5n.large, us-east-1) |

---

## Connect

```bash
ssh -i ~/.ssh/kraken_project.pem ec2-user@54.167.228.52
```

### From Windows (PowerShell)
```powershell
ssh -i C:\Users\iskid\OneDrive\Desktop\kraken_project.pem ec2-user@54.167.228.52
```

### From Windows (PuTTY)
1. Convert the `.pem` to `.ppk` using **PuTTYgen** → Load → Save private key
2. Open PuTTY → Host: `ec2-user@54.167.228.52` → SSH → Auth → browse to `.ppk`

---

## Key file permissions (Linux/Mac only)

The `.pem` file must be read-only by your user or SSH will refuse it:

```bash
chmod 400 ~/.ssh/kraken_project.pem
```

---

## Bot management

```bash
# Live log stream
sudo journalctl -u kraken-bot -f

# Last 100 lines
sudo journalctl -u kraken-bot -n 100 --no-pager

# Service status
sudo systemctl status kraken-bot

# Stop the bot
sudo systemctl stop kraken-bot

# Start the bot
sudo systemctl start kraken-bot

# Restart after a config/code change
sudo systemctl restart kraken-bot
```

---

## Project location on server

```
/opt/kraken_bot/
├── .env                  # credentials + trading config
├── launcher.py           # starts all pairs
├── main.py               # single-pair entrypoint
├── pairs/                # per-pair .env overrides
├── src/                  # trading logic
├── logs/                 # per-pair log files
└── venv/                 # Python virtualenv
```

```bash
# View .env on server
sudo cat /opt/kraken_bot/.env

# Tail a specific pair log
tail -f /opt/kraken_bot/logs/xrp.log

# List all running pair processes
ps aux | grep main.py
```

---

## Re-deploy code from local machine

Run this from the `kraken_ai_trading/` project root:

```bash
bash cloud_resource/deploy.sh 54.167.228.52 ~/.ssh/kraken_project.pem
```

This rsyncs all source files, copies `.env`, reinstalls Python deps, and restarts the bot.

---

## Monitoring dashboards

| Service | URL |
|---|---|
| Grafana | http://54.167.228.52:3000 |
| Prometheus | http://54.167.228.52:9090 |

---

## Troubleshoot connection issues

**"Permission denied (publickey)"**
- Wrong key file — confirm you're using `kraken_project.pem`
- Wrong permissions — run `chmod 400 ~/.ssh/kraken_project.pem`
- Wrong user — must be `ec2-user`, not `ubuntu` or `root`

**"Connection timed out"**
- Instance may be stopped — check AWS console or run:
  ```bash
  aws ec2 describe-instances --instance-ids i-0cb133a2b500dcc23 \
    --query 'Reservations[0].Instances[0].State.Name'
  ```
- Start it if stopped:
  ```bash
  aws ec2 start-instances --instance-ids i-0cb133a2b500dcc23
  ```

**"Host key verification failed"**
- IP reassigned (shouldn't happen with Elastic IP) — clear stale entry:
  ```bash
  ssh-keygen -R 54.167.228.52
  ```
