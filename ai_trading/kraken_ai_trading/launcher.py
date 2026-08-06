"""
Multi-pair launcher — runs one isolated bot process per trading pair.

Usage:
    python launcher.py                  # runs all pairs found in pairs/*.env
    python launcher.py xrp btc         # runs only xrp.env and btc.env
    python launcher.py --dry-run xrp   # force DRY_RUN=true regardless of env file
    python launcher.py --list          # list available pairs and exit

Each pair runs as a separate subprocess:  python main.py --env pairs/<pair>.env
If a pair crashes it is automatically restarted with exponential backoff (5s → 60s max).
Press Ctrl+C to stop all pairs gracefully (each bot cancels its open orders first).

Logs are written to:
    logs/<pair>.log   — full pair log
    stdout            — all pairs interleaved, prefixed with [PAIR]
"""

import argparse
import asyncio
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PAIRS_DIR = Path("pairs")
LOGS_DIR = Path("logs")
RESTART_DELAY_INIT = 5.0
RESTART_DELAY_MAX = 60.0

# Seconds between DMS calls for successive pairs (0s, 20s, 40s, …)
# Keeps three pairs from hitting the Kraken REST endpoint simultaneously,
# which would trigger EAPI:Invalid nonce on the shared API key.
DMS_JITTER_STEP = 20


# ---------------------------------------------------------------------------
# Process cleanup
# ---------------------------------------------------------------------------

def _kill_stale_processes() -> None:
    """
    Kill all launcher and bot processes from previous sessions before starting fresh.
    Runs synchronously at CLI entry so there is never more than one active launcher.
    """
    my_pid = os.getpid()

    # Kill other launcher.py Python processes (match "python.*launcher.py" to avoid
    # matching bash wrappers that have "launcher.py" in their eval string)
    result = subprocess.run(
        ["pgrep", "-f", "python.*launcher\\.py"],
        capture_output=True, text=True,
    )
    pids_to_kill = []
    for pid_str in result.stdout.splitlines():
        try:
            pid = int(pid_str)
            if pid != my_pid:
                os.kill(pid, signal.SIGTERM)
                pids_to_kill.append(pid)
        except (ValueError, ProcessLookupError):
            pass

    # Kill all bot processes
    subprocess.run(["pkill", "-TERM", "-f", "python.*main\\.py"], capture_output=True)
    time.sleep(3)

    # Force-kill anything still alive
    subprocess.run(["pkill", "-9", "-f", "python.*main\\.py"], capture_output=True)
    for pid in pids_to_kill:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


async def _kill_existing_pair(tag: str) -> None:
    """Kill any previous bot process for this pair using its PID file."""
    pid_file = LOGS_DIR / f"{tag.lower()}.pid"
    if not pid_file.exists():
        return
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, signal.SIGTERM)
        print(f"[LAUNCHER] {tag} killed old process pid={pid}", flush=True)
        # Give it up to 5s to exit cleanly (cancels orders), then force-kill
        for _ in range(10):
            await asyncio.sleep(0.5)
            try:
                os.kill(pid, 0)  # 0 = check existence only
            except ProcessLookupError:
                break  # process is gone
        else:
            # Still alive after 5s — force kill
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"[LAUNCHER] {tag} force-killed pid={pid}", flush=True)
            except ProcessLookupError:
                pass
    except (ValueError, ProcessLookupError, PermissionError):
        pass
    finally:
        pid_file.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Output streaming
# ---------------------------------------------------------------------------

async def _stream(stream: asyncio.StreamReader, tag: str, log_fh) -> None:
    """Read lines from subprocess stdout, prefix with [TAG], echo + write to log."""
    async for raw in stream:
        line = raw.decode(errors="replace").rstrip()
        out = f"[{tag}] {line}"
        print(out, flush=True)
        log_fh.write(out + "\n")
        log_fh.flush()


# ---------------------------------------------------------------------------
# Single-pair lifecycle
# ---------------------------------------------------------------------------

async def _run_once(
    env_file: Path,
    tag: str,
    stop: asyncio.Event,
    log_fh,
    force_dry_run: bool,
    dms_jitter: int = 0,
) -> int:
    """Spawn one bot process. Returns its exit code."""
    env = {**os.environ, "BOT_PAIR": tag, "DMS_INITIAL_JITTER_SECONDS": str(dms_jitter), "PYTHONUNBUFFERED": "1"}
    if force_dry_run:
        env["DRY_RUN"] = "true"

    proc = await asyncio.create_subprocess_exec(
        sys.executable, "main.py", "--env", str(env_file),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )
    print(f"[LAUNCHER] {tag} started  pid={proc.pid}", flush=True)

    stream_task = asyncio.create_task(_stream(proc.stdout, tag, log_fh))

    # Wait for the process to exit OR for a global stop signal
    proc_done = asyncio.create_task(proc.wait())
    stop_fired = asyncio.create_task(stop.wait())
    await asyncio.wait([proc_done, stop_fired], return_when=asyncio.FIRST_COMPLETED)

    if not proc_done.done():
        # Stop was requested — send SIGTERM so the bot cancels its orders
        proc.terminate()
        try:
            await asyncio.wait_for(proc.wait(), timeout=15)
        except asyncio.TimeoutError:
            proc.kill()
        proc_done.cancel()

    stop_fired.cancel()
    await stream_task   # drain remaining output
    return proc.returncode or 0


async def run_pair(
    env_file: Path,
    stop: asyncio.Event,
    force_dry_run: bool = False,
    startup_delay: float = 0.0,
    dms_jitter: int = 0,
) -> None:
    """Manage a single pair: spawn, stream, auto-restart on crash."""
    tag = env_file.stem.upper()
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_path = LOGS_DIR / f"{env_file.stem}.log"
    backoff = RESTART_DELAY_INIT

    # Kill any previous instance of this pair before starting a new one
    await _kill_existing_pair(tag)

    # Stagger startup so all pairs don't hit the Kraken REST nonce check simultaneously
    if startup_delay > 0:
        print(f"[LAUNCHER] {tag} starting in {startup_delay:.0f}s...", flush=True)
        try:
            await asyncio.wait_for(asyncio.shield(stop.wait()), timeout=startup_delay)
            return  # stop fired during delay
        except asyncio.TimeoutError:
            pass

    with open(log_path, "a") as log_fh:
        log_fh.write(f"\n=== {tag} session {datetime.now().isoformat()} ===\n")

        while not stop.is_set():
            code = await _run_once(env_file, tag, stop, log_fh, force_dry_run, dms_jitter)

            if stop.is_set():
                break

            msg = f"[LAUNCHER] {tag} exited (code={code}) — restarting in {backoff:.0f}s"
            print(msg, flush=True)
            log_fh.write(msg + "\n")
            log_fh.flush()

            # Sleep for backoff duration, but wake immediately if stop fires
            try:
                await asyncio.wait_for(asyncio.shield(stop.wait()), timeout=backoff)
                break
            except asyncio.TimeoutError:
                pass

            backoff = min(backoff * 2, RESTART_DELAY_MAX)

    print(f"[LAUNCHER] {tag} done", flush=True)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main(pairs: list[str], force_dry_run: bool) -> None:
    # Clear stale slot state from any previous session before any pair starts
    try:
        from src.trading.trade_slots import clear_slots
        clear_slots()
        print("[LAUNCHER] Trade slots cleared for fresh session", flush=True)
    except Exception as e:
        print(f"[LAUNCHER] Warning: could not clear trade slots: {e}", flush=True)
    if pairs:
        # Explicit pairs requested — skip scanner gate, start exactly what was asked for
        env_files = []
        for p in pairs:
            f = PAIRS_DIR / f"{p.lower()}.env"
            if not f.exists():
                print(f"[LAUNCHER] ERROR: {f} not found", flush=True)
                raise SystemExit(1)
            env_files.append(f)
    else:
        all_env_files = sorted(PAIRS_DIR.glob("*.env"))
        if not all_env_files:
            print(f"[LAUNCHER] No .env files found in {PAIRS_DIR}/", flush=True)
            print(f"           Create pairs/xrp.env, pairs/btc.env, etc. first.", flush=True)
            raise SystemExit(1)

        # Scanner gate + slot enforcement:
        #   Step 1 — Always start bots for pairs with open positions (must keep SL/TP live).
        #   Step 2 — Count vacant slots = MAX_ACTIVE_TRADES - open_positions.
        #   Step 3 — Fill vacant slots with eligible pairs from the market scanner.
        #   Result — Total running bots never exceeds MAX_ACTIVE_TRADES.
        MAX_ACTIVE_TRADES = int(os.getenv("MAX_ACTIVE_TRADES", "5"))
        try:
            from market_scanner_once import eligible_kraken_pairs, get_open_position_symbols

            # Step 1: pairs with real open positions on exchange — must always run
            print("[LAUNCHER] Checking open positions on Kraken ...", flush=True)
            open_syms  = get_open_position_symbols()
            open_files = [f for f in all_env_files if f.stem.upper() in open_syms]
            print(
                f"[LAUNCHER] Active positions ({len(open_files)}/{MAX_ACTIVE_TRADES}): "
                f"{sorted(f.stem.upper() for f in open_files)}",
                flush=True,
            )

            # Step 2: how many new slots are available
            vacant = max(0, MAX_ACTIVE_TRADES - len(open_files))
            print(
                f"[LAUNCHER] Vacant slots: {vacant}  "
                f"(max={MAX_ACTIVE_TRADES} − active={len(open_files)})",
                flush=True,
            )

            # Step 3: fill vacant slots with scanner-eligible pairs (no existing position)
            if vacant > 0:
                eligible  = eligible_kraken_pairs()
                new_files = [
                    f for f in all_env_files
                    if f.stem.upper() in eligible and f.stem.upper() not in open_syms
                ][:vacant]
                print(
                    f"[LAUNCHER] Adding {len(new_files)}/{vacant} eligible pair(s): "
                    f"{[f.stem.upper() for f in new_files]}",
                    flush=True,
                )
                env_files = open_files + new_files
            else:
                print(
                    f"[LAUNCHER] All {MAX_ACTIVE_TRADES} slots occupied — "
                    "no new entries until a position closes",
                    flush=True,
                )
                env_files = open_files

            if not env_files:
                # No open positions, scanner returned nothing — start eligible up to cap
                eligible  = eligible_kraken_pairs() if vacant > 0 else set()
                env_files = [f for f in all_env_files if f.stem.upper() in eligible][:MAX_ACTIVE_TRADES]
            if not env_files:
                print("[LAUNCHER] Scanner gate: no eligible pairs found — falling back to all", flush=True)
                env_files = all_env_files

        except Exception as exc:
            print(f"[LAUNCHER] Scanner gate error ({exc}) — starting all configured pairs", flush=True)
            env_files = all_env_files

    if not env_files:
        print(f"[LAUNCHER] No .env files found in {PAIRS_DIR}/", flush=True)
        raise SystemExit(1)

    names = [f.stem.upper() for f in env_files]
    dry_tag = "  [FORCE DRY-RUN]" if force_dry_run else ""
    print(f"[LAUNCHER] Starting {len(env_files)} pair(s): {names}{dry_tag}", flush=True)
    print(f"[LAUNCHER] Logs → {LOGS_DIR.resolve()}/", flush=True)
    print(f"[LAUNCHER] Press Ctrl+C to stop all pairs gracefully\n", flush=True)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()

    def _handle_signal() -> None:
        print("\n[LAUNCHER] Shutdown — waiting for all pairs to cancel orders...", flush=True)
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _handle_signal)

    tasks = [
        asyncio.create_task(run_pair(
            f, stop, force_dry_run,
            startup_delay=i * 3,
            dms_jitter=i * DMS_JITTER_STEP,
        ))
        for i, f in enumerate(env_files)
    ]
    await asyncio.gather(*tasks, return_exceptions=True)
    print("[LAUNCHER] All pairs stopped.", flush=True)


def cli() -> None:
    parser = argparse.ArgumentParser(
        description="Multi-pair Kraken trading bot launcher",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "pairs",
        nargs="*",
        metavar="PAIR",
        help="Pairs to run (e.g. xrp btc eth). Default: all pairs in pairs/*.env",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force DRY_RUN=true for all pairs regardless of their env file",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List available pair configs and exit",
    )
    args = parser.parse_args()

    if args.list:
        files = sorted(PAIRS_DIR.glob("*.env"))
        if not files:
            print(f"No pairs configured in {PAIRS_DIR}/")
        else:
            print("Available pairs:")
            for f in files:
                print(f"  {f.stem.upper():10s}  →  {f}")
        return

    print("[LAUNCHER] Stopping any previous launcher and bot processes...", flush=True)
    _kill_stale_processes()
    asyncio.run(main(args.pairs, args.dry_run))


if __name__ == "__main__":
    cli()
