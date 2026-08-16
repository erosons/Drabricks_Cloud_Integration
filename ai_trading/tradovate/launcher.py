"""Multi-product launcher (§18-§19) — one isolated process per product.

    python launcher.py                # every product with trade: true
    python launcher.py MES MNQ       # explicit subset
    python launcher.py --list        # show tradable products and exit
    python launcher.py --synthetic   # pass --synthetic through (dry_run only)

Each product runs as:  python main.py --product <SYM>
with BOT_PRODUCT and METRICS_PORT (8100+N) in its environment. A crashed
product restarts with exponential backoff (5s → 60s); one product crashing
never touches the others. Ctrl+C stops everything gracefully.

Logs: logs/<product>.log plus interleaved stdout prefixed [PRODUCT].
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from src.config_loader import load_config
from src.utils.logger import get_logger

ROOT = Path(__file__).parent
RESTART_DELAY_INIT = 5.0
RESTART_DELAY_MAX = 60.0

log = get_logger("launcher")


async def run_product(symbol: str, port: int, extra_args: list[str],
                      stop: asyncio.Event) -> None:
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(exist_ok=True)
    delay = RESTART_DELAY_INIT
    while not stop.is_set():
        env = {**os.environ, "BOT_PRODUCT": symbol, "METRICS_PORT": str(port)}
        logfile = open(logs_dir / f"{symbol}.log", "ab")
        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(ROOT / "main.py"), "--product", symbol,
            *extra_args, env=env, cwd=ROOT,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        log.info("[%s] started pid=%d metrics=:%d", symbol, proc.pid, port)

        async def pump():
            async for line in proc.stdout:
                logfile.write(line)
                logfile.flush()
                sys.stdout.write(f"[{symbol}] {line.decode(errors='replace')}")

        pump_task = asyncio.create_task(pump())
        stopper = asyncio.create_task(stop.wait())
        waiter = asyncio.create_task(proc.wait())
        done, _ = await asyncio.wait({waiter, stopper},
                                     return_when=asyncio.FIRST_COMPLETED)
        if stopper in done:
            proc.terminate()
            await proc.wait()
            await pump_task
            logfile.close()
            log.info("[%s] stopped", symbol)
            return

        await pump_task
        logfile.close()
        code = waiter.result()
        if code == 0:
            log.info("[%s] exited cleanly", symbol)
            return
        log.warning("[%s] crashed (exit %d) — restart in %.0fs", symbol, code, delay)
        try:
            await asyncio.wait_for(stop.wait(), timeout=delay)
            return
        except asyncio.TimeoutError:
            delay = min(delay * 2, RESTART_DELAY_MAX)


async def amain() -> int:
    parser = argparse.ArgumentParser(description="Multi-product launcher")
    parser.add_argument("products", nargs="*",
                        help="subset of products (default: all trade: true)")
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--synthetic", action="store_true")
    parser.add_argument("--ticks", type=int)
    args = parser.parse_args()

    config = load_config(ROOT / "config")
    tradable = list(config.tradable_products)
    if args.list:
        for i, sym in enumerate(tradable):
            print(f"{sym}  (metrics :{config.raw['monitoring']['metrics_base_port'] + i})")
        return 0

    selected = args.products or tradable
    unknown = [s for s in selected if s not in config.products]
    if unknown:
        log.error("unknown products: %s", unknown)
        return 2
    not_tradable = [s for s in selected if not config.products[s].trade]
    if not_tradable:
        log.error("products without trade: true in products.yaml: %s", not_tradable)
        return 2

    extra = ["--synthetic"] if args.synthetic else []
    if args.ticks:
        extra += ["--ticks", str(args.ticks)]

    base_port = int(config.raw["monitoring"]["metrics_base_port"])
    stop = asyncio.Event()

    def request_stop():
        log.info("shutdown requested — stopping all products")
        stop.set()

    loop = asyncio.get_running_loop()
    import signal as _signal
    for sig in (_signal.SIGINT, _signal.SIGTERM):
        loop.add_signal_handler(sig, request_stop)

    log.info("launching %d product process(es): %s", len(selected), selected)
    await asyncio.gather(*(
        run_product(sym, base_port + i, extra, stop)
        for i, sym in enumerate(selected)))
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(amain()))
