"""Config loader tests — the happy path runs against the REAL config files,
so any config edit that breaks a design contract fails CI immediately."""

import shutil
from pathlib import Path

import pytest
import yaml

from src.config_loader import ConfigError, ExecutionMode, load_config

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"


def _copy_config(tmp_path: Path) -> Path:
    dst = tmp_path / "config"
    shutil.copytree(CONFIG_DIR, dst)
    return dst


def _rewrite(path: Path, mutate) -> None:
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data))


class TestRealConfig:
    def test_loads_and_validates(self):
        cfg = load_config(CONFIG_DIR)
        assert cfg.mode is ExecutionMode.DRY_RUN
        assert len(cfg.products) >= 40
        assert cfg.trail_provider == "quadrant"
        assert cfg.router_selection_order == [
            "eligibility", "regime_specificity", "priority", "config_order"]

    def test_only_order_flow_scalp_enabled(self):
        cfg = load_config(CONFIG_DIR)
        enabled = [s.name for s in cfg.strategies.values() if s.enabled]
        assert enabled == ["order_flow_scalp"]

    def test_ym_quadrant_geometry_matches_readme_example(self):
        # README §13: YM, $500 stop, RR 3, tick_value $5 →
        # stop 100 ticks, target 300 ticks, quadrant step 75 ticks
        cfg = load_config(CONFIG_DIR)
        geo = cfg.products["YM"].geometry()
        assert geo.stop_ticks == 100
        assert geo.tp_ticks == 300
        assert geo.trail_step_ticks == 75
        assert geo.n_steps == 4
        assert geo.stop_after_milestone_ticks(1) == 0      # Q1 → break-even
        assert geo.stop_after_milestone_ticks(3) == 150    # Q3 → +1.5R

    def test_every_product_has_positive_geometry(self):
        cfg = load_config(CONFIG_DIR)
        for product in cfg.products.values():
            geo = product.geometry()
            assert geo.stop_ticks >= 1
            assert geo.tp_ticks > geo.stop_ticks
            assert 1 <= geo.trail_step_ticks <= geo.tp_ticks


class TestContractViolations:
    def test_missing_risk_block_fails(self, tmp_path):
        cfg_dir = _copy_config(tmp_path)
        _rewrite(cfg_dir / "products.yaml",
                 lambda d: d["products"]["YM"].pop("risk"))
        with pytest.raises(ConfigError, match="YM.*risk block missing"):
            load_config(cfg_dir)

    def test_missing_risk_key_fails(self, tmp_path):
        cfg_dir = _copy_config(tmp_path)
        _rewrite(cfg_dir / "products.yaml",
                 lambda d: d["products"]["YM"]["risk"].pop("trail_step_pct"))
        with pytest.raises(ConfigError, match="trail_step_pct"):
            load_config(cfg_dir)

    def test_two_trail_providers_enabled_fails(self, tmp_path):
        cfg_dir = _copy_config(tmp_path)

        def enable_second(d):
            providers = d["shared_services"]["trailing_exit_engine"]["providers"]
            providers["supertrend"]["enabled"] = True

        _rewrite(cfg_dir / "config.yaml", enable_second)
        with pytest.raises(ConfigError, match="exactly ONE provider"):
            load_config(cfg_dir)

    def test_zero_trail_providers_enabled_fails(self, tmp_path):
        cfg_dir = _copy_config(tmp_path)

        def disable_all(d):
            providers = d["shared_services"]["trailing_exit_engine"]["providers"]
            for cfg in providers.values():
                cfg["enabled"] = False

        _rewrite(cfg_dir / "config.yaml", disable_all)
        with pytest.raises(ConfigError, match="exactly ONE provider"):
            load_config(cfg_dir)

    def test_enabled_strategy_without_playbook_card_fails(self, tmp_path):
        cfg_dir = _copy_config(tmp_path)
        (cfg_dir / "playbook" / "order_flow_scalp.yaml").unlink()
        with pytest.raises(ConfigError, match="playbook card"):
            load_config(cfg_dir)

    def test_router_handoff_must_be_flat_only(self, tmp_path):
        cfg_dir = _copy_config(tmp_path)
        _rewrite(cfg_dir / "config.yaml",
                 lambda d: d["shared_services"]["strategy_router"]
                 .__setitem__("handoff", "immediate"))
        with pytest.raises(ConfigError, match="flat_only"):
            load_config(cfg_dir)

    def test_all_errors_reported_together(self, tmp_path):
        cfg_dir = _copy_config(tmp_path)
        _rewrite(cfg_dir / "products.yaml",
                 lambda d: (d["products"]["YM"].pop("risk"),
                            d["products"]["ES"].pop("risk")))
        with pytest.raises(ConfigError) as exc:
            load_config(cfg_dir)
        assert len(exc.value.errors) == 2
