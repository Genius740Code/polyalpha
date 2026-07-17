"""
Tests for paper trading configuration loading from environment variables and presets.
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from polyalpha.core.env import get_paper_config_from_env
from polyalpha.trading.paper_config import (
    list_presets,
    get_preset,
    get_paper_config_from_preset,
    print_preset,
    add_preset,
)
from polyalpha.trading.paper import PaperConfig


class TestEnvironmentConfig:
    """Test loading paper trading configuration from environment variables."""

    def test_default_config(self):
        """Test that default values are returned when no env vars are set."""
        # Clear any existing env vars
        for key in list(os.environ.keys()):
            if key.startswith("POLYALPHA_PAPER_"):
                del os.environ[key]
        
        config = get_paper_config_from_env()
        
        assert config["fee_mode"] == "custom"
        assert config["market_category"] == "crypto"
        assert config["custom_fee_rate"] == 0.02
        assert config["enable_rebates"] is True
        assert config["execution_delay_ms"] == 0
        assert config["slippage_pct"] == 0.0
        assert config["fill_probability"] == 1.0
        assert config["check_mode"] == "continuous"
        assert config["enable_risk_management"] is True
        assert config["max_daily_loss"] == 500.0
        assert config["max_trades_per_day"] == 100

    def test_fee_mode_from_env(self):
        """Test loading fee mode from environment."""
        os.environ["POLYALPHA_PAPER_FEE_MODE"] = "polymarket"
        config = get_paper_config_from_env()
        assert config["fee_mode"] == "polymarket"
        del os.environ["POLYALPHA_PAPER_FEE_MODE"]

    def test_custom_fee_rate_from_env(self):
        """Test loading custom fee rate from environment."""
        os.environ["POLYALPHA_PAPER_CUSTOM_FEE_RATE"] = "0.03"
        config = get_paper_config_from_env()
        assert config["custom_fee_rate"] == 0.03
        del os.environ["POLYALPHA_PAPER_CUSTOM_FEE_RATE"]

    def test_execution_delay_from_env(self):
        """Test loading execution delay from environment."""
        os.environ["POLYALPHA_PAPER_EXECUTION_DELAY_MS"] = "5000"
        config = get_paper_config_from_env()
        assert config["execution_delay_ms"] == 5000
        del os.environ["POLYALPHA_PAPER_EXECUTION_DELAY_MS"]

    def test_slippage_from_env(self):
        """Test loading slippage from environment."""
        os.environ["POLYALPHA_PAPER_SLIPPAGE_PCT"] = "0.05"
        config = get_paper_config_from_env()
        assert config["slippage_pct"] == 0.05
        del os.environ["POLYALPHA_PAPER_SLIPPAGE_PCT"]

    def test_fill_probability_from_env(self):
        """Test loading fill probability from environment."""
        os.environ["POLYALPHA_PAPER_FILL_PROBABILITY"] = "0.75"
        config = get_paper_config_from_env()
        assert config["fill_probability"] == 0.75
        del os.environ["POLYALPHA_PAPER_FILL_PROBABILITY"]

    def test_check_mode_string_from_env(self):
        """Test loading check mode string from environment."""
        os.environ["POLYALPHA_PAPER_CHECK_MODE"] = "once"
        config = get_paper_config_from_env()
        assert config["check_mode"] == "once"
        del os.environ["POLYALPHA_PAPER_CHECK_MODE"]

    def test_check_mode_integer_from_env(self):
        """Test loading check mode integer from environment."""
        os.environ["POLYALPHA_PAPER_CHECK_MODE"] = "5"
        config = get_paper_config_from_env()
        assert config["check_mode"] == 5
        del os.environ["POLYALPHA_PAPER_CHECK_MODE"]

    def test_check_mode_invalid_defaults_to_continuous(self):
        """Test that invalid check mode defaults to continuous."""
        os.environ["POLYALPHA_PAPER_CHECK_MODE"] = "invalid"
        config = get_paper_config_from_env()
        assert config["check_mode"] == "continuous"
        del os.environ["POLYALPHA_PAPER_CHECK_MODE"]

    def test_enable_rebates_true_from_env(self):
        """Test loading enable rebates true from environment."""
        os.environ["POLYALPHA_PAPER_ENABLE_REBATES"] = "true"
        config = get_paper_config_from_env()
        assert config["enable_rebates"] is True
        del os.environ["POLYALPHA_PAPER_ENABLE_REBATES"]

    def test_enable_rebates_false_from_env(self):
        """Test loading enable rebates false from environment."""
        os.environ["POLYALPHA_PAPER_ENABLE_REBATES"] = "false"
        config = get_paper_config_from_env()
        assert config["enable_rebates"] is False
        del os.environ["POLYALPHA_PAPER_ENABLE_REBATES"]

    def test_risk_management_from_env(self):
        """Test loading risk management settings from environment."""
        os.environ["POLYALPHA_PAPER_MAX_DAILY_LOSS"] = "1000.0"
        os.environ["POLYALPHA_PAPER_MAX_TRADES_PER_DAY"] = "50"
        os.environ["POLYALPHA_PAPER_MAX_RISK_PER_TRADE"] = "0.05"
        
        config = get_paper_config_from_env()
        assert config["max_daily_loss"] == 1000.0
        assert config["max_trades_per_day"] == 50
        assert config["max_risk_per_trade"] == 0.05
        
        del os.environ["POLYALPHA_PAPER_MAX_DAILY_LOSS"]
        del os.environ["POLYALPHA_PAPER_MAX_TRADES_PER_DAY"]
        del os.environ["POLYALPHA_PAPER_MAX_RISK_PER_TRADE"]

    def test_env_config_creates_valid_paper_config(self):
        """Test that env config can be used to create a valid PaperConfig."""
        config_dict = get_paper_config_from_env()
        paper_config = PaperConfig(**config_dict)
        assert paper_config.fee_mode == "custom"
        assert paper_config.custom_fee_rate == 0.02


class TestConfigurationPresets:
    """Test configuration presets."""

    def test_list_presets(self):
        """Test listing available presets."""
        presets = list_presets()
        assert isinstance(presets, list)
        assert len(presets) > 0
        assert "REALISTIC" in presets
        assert "CONSERVATIVE" in presets
        assert "TEST" in presets

    def test_get_preset_case_insensitive(self):
        """Test that preset names are case-insensitive."""
        preset1 = get_preset("realistic")
        preset2 = get_preset("REALISTIC")
        preset3 = get_preset("Realistic")
        
        assert preset1 == preset2 == preset3

    def test_get_preset_invalid_raises_error(self):
        """Test that invalid preset name raises ValueError."""
        with pytest.raises(ValueError, match="Unknown preset"):
            get_preset("INVALID_PRESET")

    def test_get_preset_returns_dict(self):
        """Test that get_preset returns a dictionary."""
        preset = get_preset("REALISTIC")
        assert isinstance(preset, dict)
        assert "fee_mode" in preset
        assert "execution_delay_ms" in preset
        assert "slippage_pct" in preset

    def test_get_paper_config_from_preset(self):
        """Test getting a PaperConfig object from preset."""
        config = get_paper_config_from_preset("REALISTIC")
        assert isinstance(config, PaperConfig)
        assert config.fee_mode == "polymarket"
        assert config.execution_delay_ms == 2000

    def test_conservative_preset_values(self):
        """Test CONSERVATIVE preset has expected values."""
        config = get_paper_config_from_preset("CONSERVATIVE")
        assert config.fee_mode == "polymarket"
        assert config.execution_delay_ms == 500
        assert config.slippage_pct == 0.01
        assert config.max_daily_loss == 100.0
        assert config.max_trades_per_day == 20
        assert config.max_risk_per_trade == 0.01

    def test_realistic_preset_values(self):
        """Test REALISTIC preset has expected values."""
        config = get_paper_config_from_preset("REALISTIC")
        assert config.fee_mode == "polymarket"
        assert config.execution_delay_ms == 2000
        assert config.slippage_pct == 0.03
        assert config.max_daily_loss == 500.0
        assert config.max_trades_per_day == 100
        assert config.max_risk_per_trade == 0.02

    def test_zero_fee_preset_values(self):
        """Test ZERO_FEE preset has expected values."""
        config = get_paper_config_from_preset("ZERO_FEE")
        assert config.fee_mode == "zero"
        assert config.execution_delay_ms == 0
        assert config.slippage_pct == 0.0
        assert config.fill_probability == 1.0

    def test_test_preset_values(self):
        """Test TEST preset has expected values."""
        config = get_paper_config_from_preset("TEST")
        assert config.fee_mode == "zero"
        assert config.enable_risk_management is False
        assert config.max_daily_loss == 10000.0
        assert config.max_trades_per_day == 1000

    def test_add_preset(self):
        """Test adding a custom preset."""
        custom_config = {
            "fee_mode": "custom",
            "custom_fee_rate": 0.01,
            "execution_delay_ms": 100,
            "slippage_pct": 0.0,
        }
        add_preset("CUSTOM_TEST", custom_config)
        
        retrieved = get_preset("CUSTOM_TEST")
        assert retrieved["fee_mode"] == "custom"
        assert retrieved["custom_fee_rate"] == 0.01

    def test_print_preset(self, capsys):
        """Test printing a preset."""
        print_preset("REALISTIC")
        captured = capsys.readouterr()
        assert "REALISTIC" in captured.out
        assert "fee_mode" in captured.out

    def test_print_preset_invalid_raises_error(self):
        """Test that printing invalid preset raises ValueError."""
        with pytest.raises(ValueError, match="Unknown preset"):
            print_preset("INVALID_PRESET")


class TestPaperConfigValidation:
    """Test PaperConfig validation with loaded values."""

    def test_env_config_passes_validation(self):
        """Test that config from env passes PaperConfig validation."""
        config_dict = get_paper_config_from_env()
        # Should not raise any exceptions
        config = PaperConfig(**config_dict)
        assert config is not None

    def test_preset_config_passes_validation(self):
        """Test that all preset configs pass validation."""
        for preset_name in list_presets():
            config = get_paper_config_from_preset(preset_name)
            assert config is not None
            assert isinstance(config, PaperConfig)

    def test_invalid_fee_mode_raises_error(self):
        """Test that invalid fee mode raises ValueError."""
        with pytest.raises(ValueError, match="fee_mode must be"):
            PaperConfig(fee_mode="invalid")

    def test_negative_fee_rate_raises_error(self):
        """Test that negative fee rate raises ValueError."""
        with pytest.raises(ValueError, match="custom_fee_rate must be"):
            PaperConfig(custom_fee_rate=-0.01)

    def test_invalid_slippage_raises_error(self):
        """Test that invalid slippage raises ValueError."""
        with pytest.raises(ValueError, match="slippage_pct must be"):
            PaperConfig(slippage_pct=-0.01)

    def test_invalid_fill_probability_raises_error(self):
        """Test that invalid fill probability raises ValueError."""
        with pytest.raises(ValueError, match="fill_probability must be"):
            PaperConfig(fill_probability=1.5)

    def test_invalid_risk_per_trade_raises_error(self):
        """Test that invalid risk per trade raises ValueError."""
        with pytest.raises(ValueError, match="max_risk_per_trade must be"):
            PaperConfig(max_risk_per_trade=1.5)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
