"""Active-contract resolver (§4).

Once per day: pull Volume & OI for every product with trade: true, store the
contract with the highest volume AND open interest as the ACTIVE contract.
If volume and OI disagree, prefer max volume (config selection_rule). A roll
is flagged when the winner changes; the trading process finishes the session
on the old month and subscribes to the new one at the next session open.

CLI:  python -m src.reference.contract_resolver --once
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass

from src.config_loader import AppConfig, load_config
from src.reference.volume_oi import CMEVolumeFetcher, ContractVolumeOI, VolumeFetchError
from src.storage.db import Database

log = logging.getLogger("contract_resolver")


@dataclass(frozen=True)
class Resolution:
    product: str
    winner: ContractVolumeOI
    roll: bool               # winner differs from the stored active contract
    agreed: bool             # volume winner and OI winner were the same month


def pick_active(records: list[ContractVolumeOI]) -> tuple[ContractVolumeOI, bool]:
    """selection_rule max_volume_and_oi: both must agree; else prefer max
    volume (§4). Returns (winner, agreed)."""
    if not records:
        raise VolumeFetchError("no contract records to pick from")
    by_volume = max(records, key=lambda r: r.volume)
    by_oi = max(records, key=lambda r: r.open_interest)
    return by_volume, by_volume.contract_code == by_oi.contract_code


def resolve_product(db: Database, records: list[ContractVolumeOI]) -> Resolution:
    winner, agreed = pick_active(records)
    current = db.get_active_contract(winner.product)
    roll = current is not None and current["contract_code"] != winner.contract_code

    for rec in records:
        db.insert_volume_oi(rec.product, rec.contract_code, rec.trade_date,
                            rec.volume, rec.open_interest)
    db.upsert_active_contract(
        winner.product, winner.contract_code, winner.contract_month,
        winner.trade_date, winner.volume, winner.open_interest,
        roll_pending=roll,
    )
    if roll:
        log.warning("[%s] ROLL: %s -> %s", winner.product,
                    current["contract_code"], winner.contract_code)
    if not agreed:
        log.warning("[%s] volume/OI disagree — using max volume: %s",
                    winner.product, winner.contract_code)
    return Resolution(winner.product, winner, roll, agreed)


def is_tradeable(db: Database, product: str, stale_after_hours: float) -> bool:
    """§4: refuse to trade if the active-contract row is missing or older
    than stale_after_hours."""
    age = db.active_contract_age_hours(product)
    return age is not None and age <= stale_after_hours


def run_once(config: AppConfig, db: Database) -> list[Resolution]:
    resolver_cfg = config.raw["contract_resolver"]
    fetcher = CMEVolumeFetcher(resolver_cfg["volume_url_template"])
    resolutions = []
    for symbol, product in config.tradable_products.items():
        try:
            records = fetcher.fetch(symbol, product.cme_slug)
            resolutions.append(resolve_product(db, records))
        except (VolumeFetchError, OSError) as exc:
            # Designed failure mode: leave the stored row untouched; trading
            # halts by itself once the row crosses stale_after_hours.
            log.error("[%s] volume/OI fetch failed: %s", symbol, exc)
    return resolutions


def main() -> int:
    parser = argparse.ArgumentParser(description="Active-contract resolver")
    parser.add_argument("--once", action="store_true", required=True,
                        help="run a single resolution pass and exit")
    parser.add_argument("--config-dir", default="config")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = load_config(args.config_dir)
    with Database(config.raw["database"]["path"]) as db:
        resolutions = run_once(config, db)
    for res in resolutions:
        print(f"{res.product}: active={res.winner.contract_code}"
              f"{' ROLL' if res.roll else ''}")
    return 0 if resolutions else 1


if __name__ == "__main__":
    raise SystemExit(main())
