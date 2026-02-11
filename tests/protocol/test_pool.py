"""Tests for the pool model."""

import pytest

from src.protocol.interest_rate import InterestRateModel, InterestRateParams
from src.protocol.pool import PoolModel, PoolState

WETH_RATE_PARAMS = InterestRateParams(
    optimal_utilization=0.92,
    base_rate=0.0,
    slope1=0.027,
    slope2=0.40,
    reserve_factor=0.15,
)


@pytest.fixture
def pool_model() -> PoolModel:
    state = PoolState(total_supply=2_800_000.0, total_debt=2_200_000.0)
    rate_model = InterestRateModel(WETH_RATE_PARAMS)
    return PoolModel(state, rate_model)


class TestPoolState:
    def test_utilization(self) -> None:
        # In Aave, total_supply = available_liquidity + total_debt
        # so U = total_debt / total_supply
        state = PoolState(total_supply=800_000.0, total_debt=200_000.0)
        # U = 200k / 800k = 0.25
        assert state.utilization == pytest.approx(0.25)

    def test_utilization_empty_pool(self) -> None:
        state = PoolState(total_supply=0.0, total_debt=0.0)
        assert state.utilization == 0.0

    def test_high_utilization(self) -> None:
        state = PoolState(total_supply=1_000_000.0, total_debt=900_000.0)
        # U = 900k / 1M = 0.9
        assert state.utilization == pytest.approx(0.9)


class TestPoolModel:
    def test_current_rates(self, pool_model: PoolModel) -> None:
        u = pool_model.utilization
        assert 0 < u < 1
        assert pool_model.borrow_rate > 0
        assert pool_model.supply_rate > 0
        assert pool_model.supply_rate < pool_model.borrow_rate

    def test_simulate_borrow(self, pool_model: PoolModel) -> None:
        result = pool_model.simulate_borrow(100_000.0)
        assert result["utilization_after"] > result["utilization_before"]
        assert result["borrow_rate_after"] > result["borrow_rate_before"]

    def test_simulate_borrow_does_not_mutate(self, pool_model: PoolModel) -> None:
        u_before = pool_model.utilization
        pool_model.simulate_borrow(100_000.0)
        assert pool_model.utilization == u_before

    def test_simulate_withdrawal(self, pool_model: PoolModel) -> None:
        result = pool_model.simulate_withdrawal(100_000.0)
        assert result["utilization_after"] > result["utilization_before"]
        assert result["borrow_rate_after"] > result["borrow_rate_before"]

    def test_simulate_withdrawal_exceeding_supply(self, pool_model: PoolModel) -> None:
        """Withdrawing more than total supply should clamp utilization to 1.0."""
        result = pool_model.simulate_withdrawal(pool_model.state.total_supply + 1_000.0)
        assert result["utilization_after"] == 1.0
        assert result["utilization_after"] >= 0.0

    def test_simulate_withdrawal_equal_to_supply(self, pool_model: PoolModel) -> None:
        """Withdrawing exactly the total supply should yield utilization 1.0."""
        result = pool_model.simulate_withdrawal(pool_model.state.total_supply)
        assert result["utilization_after"] == 1.0

    def test_simulate_liquidation_impact(self, pool_model: PoolModel) -> None:
        result = pool_model.simulate_liquidation_impact(
            liquidated_debt=50_000.0,
        )
        # Debt repaid → utilization drops (supply stays the same)
        assert result["utilization_after"] < result["utilization_before"]
        assert "borrow_rate_after" in result
