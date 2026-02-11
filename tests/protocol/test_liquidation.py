"""Tests for the liquidation model."""

import pytest

from src.protocol.emode import EModeCategory
from src.protocol.liquidation import LiquidationModel, LiquidationParams

STD_PARAMS = LiquidationParams(
    ltv=0.805,
    liquidation_threshold=0.83,
    liquidation_bonus=0.05,
)

EMODE = EModeCategory(
    category_id=1,
    label="ETH correlated",
    ltv=0.935,
    liquidation_threshold=0.955,
    liquidation_bonus=0.01,
)


@pytest.fixture
def std_model() -> LiquidationModel:
    return LiquidationModel(STD_PARAMS)


@pytest.fixture
def emode_model() -> LiquidationModel:
    return LiquidationModel(STD_PARAMS, emode=EMODE)


class TestHealthFactor:
    def test_healthy_position(self, std_model: LiquidationModel) -> None:
        hf = std_model.health_factor(collateral_value=100.0, debt_value=50.0)
        expected = (100.0 * 0.83) / 50.0
        assert hf == pytest.approx(expected)
        assert hf > 1.0

    def test_exact_liquidation(self, std_model: LiquidationModel) -> None:
        # collateral * 0.83 / debt = 1.0 => debt = collateral * 0.83
        hf = std_model.health_factor(collateral_value=100.0, debt_value=83.0)
        assert hf == pytest.approx(1.0, rel=1e-6)

    def test_underwater_position(self, std_model: LiquidationModel) -> None:
        hf = std_model.health_factor(collateral_value=100.0, debt_value=90.0)
        assert hf < 1.0

    def test_no_debt(self, std_model: LiquidationModel) -> None:
        hf = std_model.health_factor(collateral_value=100.0, debt_value=0.0)
        assert hf == float("inf")

    def test_emode_higher_threshold(self, emode_model: LiquidationModel) -> None:
        hf_emode = emode_model.health_factor(collateral_value=100.0, debt_value=90.0)
        # E-mode threshold is 0.955 vs standard 0.83
        expected = (100.0 * 0.955) / 90.0
        assert hf_emode == pytest.approx(expected)
        assert hf_emode > 1.0  # Safe under E-mode, not safe under standard


class TestCloseFactor:
    def test_healthy_position(self, std_model: LiquidationModel) -> None:
        assert std_model.close_factor(1.5) == 0.0

    def test_partial_liquidation(self, std_model: LiquidationModel) -> None:
        assert std_model.close_factor(0.98) == 0.5

    def test_boundary_095(self, std_model: LiquidationModel) -> None:
        assert std_model.close_factor(0.95) == 0.5

    def test_full_liquidation(self, std_model: LiquidationModel) -> None:
        assert std_model.close_factor(0.94) == 1.0

    def test_deeply_underwater(self, std_model: LiquidationModel) -> None:
        assert std_model.close_factor(0.5) == 1.0


class TestMaxBorrowable:
    def test_standard(self, std_model: LiquidationModel) -> None:
        max_debt = std_model.max_borrowable(collateral_value=100.0)
        assert max_debt == pytest.approx(80.5)

    def test_emode(self, emode_model: LiquidationModel) -> None:
        max_debt = emode_model.max_borrowable(collateral_value=100.0)
        assert max_debt == pytest.approx(93.5)


class TestLiquidationPriceDrop:
    def test_safe_position(self, std_model: LiquidationModel) -> None:
        drop = std_model.liquidation_price_drop(
            collateral_value=100.0, debt_value=50.0
        )
        # 1 - 50 / (100 * 0.83) = 1 - 0.6024 = 0.3976
        expected = 1.0 - 50.0 / (100.0 * 0.83)
        assert drop == pytest.approx(expected, rel=1e-6)

    def test_already_liquidatable(self, std_model: LiquidationModel) -> None:
        drop = std_model.liquidation_price_drop(
            collateral_value=100.0, debt_value=100.0
        )
        assert drop == 0.0

    def test_no_debt(self, std_model: LiquidationModel) -> None:
        drop = std_model.liquidation_price_drop(
            collateral_value=100.0, debt_value=0.0
        )
        assert drop == float("inf")


class TestDepegToLiquidation:
    def test_mellow_vault_emode(self, emode_model: LiquidationModel) -> None:
        """Example: 12K wstETH at 1.18 ETH, 10.5K WETH debt, E-mode."""
        peg = emode_model.depeg_to_liquidation(
            collateral_amount=12_000.0,
            collateral_price=1.18,
            debt_value=10_500.0,
        )
        expected = 10_500.0 / (12_000.0 * 1.18 * 0.955)
        assert peg == pytest.approx(expected, rel=1e-6)
        assert peg < 1.0  # Should be safe at current peg

    def test_already_liquidatable(self, emode_model: LiquidationModel) -> None:
        peg = emode_model.depeg_to_liquidation(
            collateral_amount=100.0,
            collateral_price=1.0,
            debt_value=100.0,
        )
        assert peg == 0.0  # Already liquidatable

    def test_no_debt(self, emode_model: LiquidationModel) -> None:
        peg = emode_model.depeg_to_liquidation(
            collateral_amount=100.0,
            collateral_price=1.18,
            debt_value=0.0,
        )
        assert peg == 0.0


class TestDepegSensitivity:
    def test_output_shape(self, emode_model: LiquidationModel) -> None:
        df = emode_model.depeg_sensitivity(
            collateral_amount=12_000.0,
            collateral_price=1.18,
            debt_value=10_500.0,
            n_points=50,
        )
        assert len(df) == 50
        assert list(df.columns) == ["peg_ratio", "health_factor"]

    def test_hf_decreases_with_depeg(self, emode_model: LiquidationModel) -> None:
        df = emode_model.depeg_sensitivity(
            collateral_amount=12_000.0,
            collateral_price=1.18,
            debt_value=10_500.0,
        )
        # HF should decrease as peg decreases
        hfs = df["health_factor"].values
        assert all(hfs[i] <= hfs[i + 1] for i in range(len(hfs) - 1))
