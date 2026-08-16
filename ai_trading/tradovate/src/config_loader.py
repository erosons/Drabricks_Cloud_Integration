"""Config loaders enforcing the design's contracts (docs/README.md §21).

Contracts enforced at load time — the bot refuses to start on violation:
  * every product carries a complete `risk:` block (§13 — no generic fallback)
  * exactly ONE trailing_exit_engine provider is enabled (§13)
  * the strategy router's selection rules are known and complete (§7)
  * every enabled strategy has a playbook card (§8 — the G1 artifact)

Also derives the quadrant-trail geometry per product (§13): stop/target/step
in ticks, from stop_loss_usd, risk_reward_ratio and trail_step_pct.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

RISK_REQUIRED_KEYS = (
    "max_contracts", "risk_per_trade_pct", "stop_loss_usd",
    "risk_reward_ratio", "trail_step_pct", "daily_loss_limit_usd",
)

ROUTER_KNOWN_RULES = ("eligibility", "regime_specificity", "priority", "config_order")


class ConfigError(Exception):
    """Raised with EVERY violation listed, not just the first."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("config validation failed:\n  - " + "\n  - ".join(errors))


class ExecutionMode(Enum):
    DRY_RUN = "dry_run"    # signals only, no orders anywhere
    DEMO = "demo"          # orders to the Tradovate demo account
    LIVE = "live"          # orders to the live account


@dataclass(frozen=True)
class QuadrantGeometry:
    """Tick-native quadrant-trail geometry (§13). Milestone k fires at
    entry + k*trail_step_ticks; the stop then moves to entry + (k-1)*step
    (k=1 → break-even). Milestone n_steps is the target: full exit."""

    stop_ticks: int
    tp_ticks: int
    trail_step_ticks: int

    @property
    def n_steps(self) -> int:
        return max(1, round(self.tp_ticks / self.trail_step_ticks))

    def milestone_ticks(self, k: int) -> int:
        return k * self.trail_step_ticks

    def stop_after_milestone_ticks(self, k: int) -> int:
        """Stop offset from entry (in ticks) after milestone k; negative
        before break-even is never returned — k >= 1 only."""
        return (k - 1) * self.trail_step_ticks


@dataclass(frozen=True)
class RiskBlock:
    max_contracts: int
    risk_per_trade_pct: float
    stop_loss_usd: float
    risk_reward_ratio: float
    trail_step_pct: float
    daily_loss_limit_usd: float

    def geometry(self, tick_value: float) -> QuadrantGeometry:
        stop_ticks = math.ceil(self.stop_loss_usd / (tick_value * self.max_contracts))
        tp_ticks = round(stop_ticks * self.risk_reward_ratio)
        trail_step = max(1, math.floor(tp_ticks * self.trail_step_pct))
        return QuadrantGeometry(stop_ticks, tp_ticks, trail_step)


@dataclass(frozen=True)
class Product:
    symbol: str
    name: str
    exchange: str
    tick_size: float
    tick_value: float
    months: tuple[str, ...]
    cme_slug: str
    risk: RiskBlock
    trade: bool
    overrides: dict = field(default_factory=dict)

    def geometry(self) -> QuadrantGeometry:
        return self.risk.geometry(self.tick_value)


@dataclass(frozen=True)
class StrategyModule:
    name: str
    tier: str
    priority: int | str
    enabled: bool
    params: dict


@dataclass
class AppConfig:
    raw: dict                      # full config.yaml for blocks not modeled yet
    mode: ExecutionMode
    products: dict[str, Product]
    strategies: dict[str, StrategyModule]
    trail_provider: str            # the single enabled provider
    router_selection_order: list[str]
    config_dir: Path

    @property
    def tradable_products(self) -> dict[str, Product]:
        return {s: p for s, p in self.products.items() if p.trade}


def _execution_mode(mode_block: dict, errors: list[str]) -> ExecutionMode:
    dry_run = mode_block.get("dry_run")
    live = mode_block.get("live_trading")
    for key, val in (("dry_run", dry_run), ("live_trading", live)):
        if not isinstance(val, bool):
            errors.append(f"mode.{key} must be a boolean, got {val!r}")
    if dry_run:
        return ExecutionMode.DRY_RUN
    return ExecutionMode.LIVE if live else ExecutionMode.DEMO


def _parse_product(symbol: str, entry: dict, errors: list[str]) -> Product | None:
    risk_raw = entry.get("risk")
    if not isinstance(risk_raw, dict):
        errors.append(f"product {symbol}: required risk block missing (§13 — no fallback)")
        return None
    missing = [k for k in RISK_REQUIRED_KEYS if k not in risk_raw]
    if missing:
        errors.append(f"product {symbol}: risk block missing {missing}")
        return None

    problems = []
    if risk_raw["max_contracts"] < 1:
        problems.append("max_contracts must be >= 1")
    if risk_raw["stop_loss_usd"] <= 0:
        problems.append("stop_loss_usd must be > 0")
    if risk_raw["risk_reward_ratio"] <= 0:
        problems.append("risk_reward_ratio must be > 0")
    if not (0 < risk_raw["trail_step_pct"] <= 1):
        problems.append("trail_step_pct must be in (0, 1]")
    if risk_raw["daily_loss_limit_usd"] <= 0:
        problems.append("daily_loss_limit_usd must be > 0")
    if entry.get("tick_size", 0) <= 0 or entry.get("tick_value", 0) <= 0:
        problems.append("tick_size and tick_value must be > 0")
    if problems:
        errors.append(f"product {symbol}: " + "; ".join(problems))
        return None

    return Product(
        symbol=symbol,
        name=entry.get("name", symbol),
        exchange=entry.get("exchange", ""),
        tick_size=float(entry["tick_size"]),
        tick_value=float(entry["tick_value"]),
        months=tuple(entry.get("months", [])),
        cme_slug=entry.get("cme_slug", ""),
        risk=RiskBlock(
            max_contracts=int(risk_raw["max_contracts"]),
            risk_per_trade_pct=float(risk_raw["risk_per_trade_pct"]),
            stop_loss_usd=float(risk_raw["stop_loss_usd"]),
            risk_reward_ratio=float(risk_raw["risk_reward_ratio"]),
            trail_step_pct=float(risk_raw["trail_step_pct"]),
            daily_loss_limit_usd=float(risk_raw["daily_loss_limit_usd"]),
        ),
        trade=bool(entry.get("trade", False)),
        overrides=entry.get("overrides", {}) or {},
    )


def _validate_trail_engine(shared: dict, errors: list[str]) -> str:
    engine = shared.get("trailing_exit_engine", {})
    providers = engine.get("providers")
    if not isinstance(providers, dict) or not providers:
        errors.append("trailing_exit_engine.providers missing or empty")
        return ""
    enabled = [name for name, cfg in providers.items()
               if isinstance(cfg, dict) and cfg.get("enabled") is True]
    if len(enabled) != 1:
        errors.append(
            "trailing_exit_engine: exactly ONE provider must be enabled, "
            f"found {len(enabled)}: {enabled or 'none'}"
        )
        return ""
    return enabled[0]


def _validate_router(shared: dict, errors: list[str]) -> list[str]:
    router = shared.get("strategy_router", {})
    order = router.get("selection_order")
    if not isinstance(order, list) or not order:
        errors.append("strategy_router.selection_order missing or empty")
        return []
    unknown = [r for r in order if r not in ROUTER_KNOWN_RULES]
    if unknown:
        errors.append(f"strategy_router: unknown selection rules {unknown}")
    if router.get("handoff") != "flat_only":
        errors.append("strategy_router.handoff must be flat_only "
                      "(open positions are never handed between modules)")
    return list(order)


def load_config(config_dir: str | Path) -> AppConfig:
    """Load and validate config.yaml + products.yaml from config_dir.
    Raises ConfigError listing every violation."""
    config_dir = Path(config_dir)
    errors: list[str] = []

    with open(config_dir / "config.yaml") as f:
        raw = yaml.safe_load(f)
    with open(config_dir / "products.yaml") as f:
        products_raw = yaml.safe_load(f)

    mode = _execution_mode(raw.get("mode", {}), errors)

    products: dict[str, Product] = {}
    catalog = products_raw.get("products")
    if not isinstance(catalog, dict) or not catalog:
        errors.append("products.yaml: products catalog missing or empty")
    else:
        for symbol, entry in catalog.items():
            product = _parse_product(symbol, entry or {}, errors)
            if product is not None:
                products[symbol] = product

    shared = raw.get("shared_services", {})
    trail_provider = _validate_trail_engine(shared, errors)
    router_order = _validate_router(shared, errors)

    strategies: dict[str, StrategyModule] = {}
    playbook_dir = config_dir / "playbook"
    for name, entry in (raw.get("strategies") or {}).items():
        entry = entry or {}
        module = StrategyModule(
            name=name,
            tier=entry.get("tier", ""),
            priority=entry.get("priority", 99),
            enabled=bool(entry.get("enabled", False)),
            params=entry.get("params", {}) or {},
        )
        if module.enabled and not (playbook_dir / f"{name}.yaml").exists():
            errors.append(f"strategy {name}: enabled but has no playbook card "
                          f"(§8 — the G1 artifact is required)")
        strategies[name] = module

    if errors:
        raise ConfigError(errors)

    return AppConfig(
        raw=raw,
        mode=mode,
        products=products,
        strategies=strategies,
        trail_provider=trail_provider,
        router_selection_order=router_order,
        config_dir=config_dir,
    )
