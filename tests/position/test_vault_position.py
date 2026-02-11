"""Tests for the vault position model."""

import pytest

from src.data.static_params import StaticDataProvider
from src.position.vault_position import VaultPosition


@pytest.fixture
def provider() -> StaticDataProvider:
    return StaticDataProvider()


@pytest.fixture
def mellow_position() -> VaultPosition:
    """Example Mellow vault position: 12K wstETH, 10.5K WETH, E-mode."""
    return VaultPosition(
        collateral_amount=12_000.0,
        debt_amount=10_500.0,
        emode_enabled=True,
    )


class TestVaultPosition:
    def test_collateral_value(
        self, mellow_position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        value = mellow_position.collateral_value(provider)
        # 12000 * 1.18 * 1.0 = 14160.0
        assert value == pytest.approx(14_160.0)

    def test_debt_value(
        self, mellow_position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        value = mellow_position.debt_value(provider)
        assert value == pytest.approx(10_500.0)

    def test_net_value(
        self, mellow_position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        net = mellow_position.net_value(provider)
        assert net == pytest.approx(14_160.0 - 10_500.0)

    def test_health_factor_emode(
        self, mellow_position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        hf = mellow_position.health_factor(provider)
        # HF = (14160 * 0.955) / 10500
        expected = (14_160.0 * 0.955) / 10_500.0
        assert hf == pytest.approx(expected, rel=1e-6)
        assert hf > 1.0  # Should be safe

    def test_health_factor_no_emode(self, provider: StaticDataProvider) -> None:
        pos = VaultPosition(
            collateral_amount=12_000.0,
            debt_amount=10_500.0,
            emode_enabled=False,
        )
        hf = pos.health_factor(provider)
        # Standard wstETH threshold = 0.81
        expected = (14_160.0 * 0.81) / 10_500.0
        assert hf == pytest.approx(expected, rel=1e-6)
        assert hf > 1.0

    def test_leverage_with_prices(
        self, mellow_position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        lev = mellow_position.leverage_with_prices(provider)
        expected = 14_160.0 / (14_160.0 - 10_500.0)
        assert lev == pytest.approx(expected, rel=1e-4)

    def test_no_debt_position(self, provider: StaticDataProvider) -> None:
        pos = VaultPosition(collateral_amount=1000.0, debt_amount=0.0)
        assert pos.health_factor(provider) == float("inf")
        assert pos.net_value(provider) == pytest.approx(1000.0 * 1.18)
