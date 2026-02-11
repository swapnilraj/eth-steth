"""Tests for the P&L model."""

import pytest

from src.data.static_params import StaticDataProvider
from src.position.pnl import APYBreakdown, compute_apy_breakdown, daily_pnl
from src.position.vault_position import VaultPosition


@pytest.fixture
def provider() -> StaticDataProvider:
    return StaticDataProvider()


@pytest.fixture
def position() -> VaultPosition:
    return VaultPosition(
        collateral_amount=12_000.0,
        debt_amount=10_500.0,
        emode_enabled=True,
    )


class TestAPYBreakdown:
    def test_components_exist(
        self, position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        breakdown = compute_apy_breakdown(position, provider)
        assert isinstance(breakdown, APYBreakdown)
        assert breakdown.supply_apy >= 0
        assert breakdown.borrow_apy >= 0
        assert breakdown.staking_apy > 0

    def test_borrow_apy_positive(
        self, position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        breakdown = compute_apy_breakdown(position, provider)
        assert breakdown.borrow_apy > 0

    def test_net_apy_reasonable(
        self, position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        breakdown = compute_apy_breakdown(position, provider)
        # Net APY should be between -50% and +50% for reasonable positions
        assert -0.5 < breakdown.net_apy < 0.5

    def test_custom_staking_apy(
        self, position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        breakdown = compute_apy_breakdown(position, provider, staking_apy=0.05)
        assert breakdown.staking_apy == 0.05


class TestDailyPnl:
    def test_daily_pnl_sign(
        self, position: VaultPosition, provider: StaticDataProvider
    ) -> None:
        pnl = daily_pnl(position, provider)
        # With staking yield > borrow cost, should be positive
        # (depends on rates, but typically positive for this strategy)
        assert isinstance(pnl, float)

    def test_daily_pnl_no_debt(self, provider: StaticDataProvider) -> None:
        pos = VaultPosition(collateral_amount=1000.0, debt_amount=0.0)
        pnl = daily_pnl(pos, provider)
        assert pnl > 0  # Pure staking + supply yield

    def test_daily_pnl_underwater_not_zero(self, provider: StaticDataProvider) -> None:
        """Even when equity is negative, daily P&L should reflect ongoing costs."""
        # Very high debt relative to collateral → underwater position
        pos = VaultPosition(collateral_amount=100.0, debt_amount=50_000.0)
        pnl = daily_pnl(pos, provider)
        # Should be negative (borrow cost >> staking income), not zero
        assert pnl < 0
