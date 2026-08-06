"""
AWS Cost Exporter — queries Cost Explorer every 30 min,
exposes costs as Prometheus gauges on port 9200.

Metrics exposed:
  aws_cost_month_total_usd          — total spend this calendar month
  aws_cost_today_usd                — spend so far today
  aws_cost_service_usd{service=...} — per-service breakdown this month
  aws_cost_ec2_usd                  — EC2 + EBS cost this month
"""

import os
import time
import logging
import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler

import boto3
from prometheus_client import Gauge, generate_latest, CONTENT_TYPE_LATEST

logging.basicConfig(level=logging.INFO, format="%(asctime)s [COST] %(message)s")
log = logging.getLogger("cost")

PORT          = int(os.getenv("COST_EXPORTER_PORT", "9200"))
INTERVAL_SEC  = int(os.getenv("COST_INTERVAL_SEC",  "1800"))   # 30 min
AWS_REGION    = os.getenv("AWS_DEFAULT_REGION", "us-east-1")

# ── Prometheus metrics ────────────────────────────────────────────────────────
month_total  = Gauge("aws_cost_month_total_usd",  "Total AWS spend this calendar month (USD)")
today_total  = Gauge("aws_cost_today_usd",        "AWS spend so far today (USD)")
ec2_total    = Gauge("aws_cost_ec2_usd",          "EC2 + EBS spend this month (USD)")
service_cost = Gauge("aws_cost_service_usd",      "AWS spend by service this month (USD)", ["service"])


def _date_range_month():
    today = datetime.date.today()
    start = today.replace(day=1).isoformat()
    end   = today.isoformat()
    return start, end


def _date_range_today():
    today = datetime.date.today()
    return today.isoformat(), (today + datetime.timedelta(days=1)).isoformat()


def fetch_costs():
    client = boto3.client(
        "ce",
        region_name="us-east-1",   # Cost Explorer is always us-east-1
        aws_access_key_id     = os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key = os.getenv("AWS_SECRET_ACCESS_KEY"),
    )

    # ── Month total ───────────────────────────────────────────────────────────
    start, end = _date_range_month()
    resp = client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
    )
    total = float(resp["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"])
    month_total.set(total)
    log.info("Month total: $%.4f", total)

    # ── Today ─────────────────────────────────────────────────────────────────
    ts, te = _date_range_today()
    try:
        resp = client.get_cost_and_usage(
            TimePeriod={"Start": ts, "End": te},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
        )
        daily = float(resp["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"])
        today_total.set(daily)
        log.info("Today so far: $%.4f", daily)
    except Exception as e:
        log.warning("Today cost fetch failed: %s", e)

    # ── Per-service breakdown ─────────────────────────────────────────────────
    resp = client.get_cost_and_usage(
        TimePeriod={"Start": start, "End": end},
        Granularity="MONTHLY",
        Metrics=["UnblendedCost"],
        GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
    )
    ec2_sum = 0.0
    for group in resp["ResultsByTime"][0]["Groups"]:
        svc  = group["Keys"][0]
        amt  = float(group["Metrics"]["UnblendedCost"]["Amount"])
        service_cost.labels(service=svc).set(amt)
        if any(k in svc for k in ("EC2", "Elastic Block")):
            ec2_sum += amt
    ec2_total.set(ec2_sum)
    log.info("EC2+EBS: $%.4f", ec2_sum)


# ── HTTP handler for Prometheus scrape ───────────────────────────────────────
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/metrics":
            data = generate_latest()
            self.send_response(200)
            self.send_header("Content-Type", CONTENT_TYPE_LATEST)
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_):
        pass   # suppress access logs


if __name__ == "__main__":
    log.info("AWS Cost Exporter starting on :%d  interval=%ds", PORT, INTERVAL_SEC)

    server = HTTPServer(("0.0.0.0", PORT), Handler)

    import threading
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info("Metrics server running on http://0.0.0.0:%d/metrics", PORT)

    # First fetch immediately, then every INTERVAL_SEC
    while True:
        try:
            fetch_costs()
        except Exception as e:
            log.error("Cost fetch error: %s", e)
        time.sleep(INTERVAL_SEC)
