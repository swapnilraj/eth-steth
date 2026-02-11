"""Tests for the liquidation cascade simulation."""

import pytest

from src.protocol.interest_rate import InterestRateParams
from src.protocol.pool import PoolState
from src.simulation.liquidation_cascade import CascadeConfig, simulate_cascade


@pytest.fixture
def pool_state() -> PoolState:
    return PoolState(total_supply=2_800_000.0, total_debt=2_200_000.0)


@pytest.fixture
def rate_params() -> InterestRateParams:
    return InterestRateParams(
        optimal_utilization=0.92,
        base_rate=0.0,
        slope1=0.027,
        slope2=0.40,
        reserve_factor=0.15,
    )


class TestCascadeSimulation:
    def test_does_not_mutate_pool_state(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        original_supply = pool_state.total_supply
        original_debt = pool_state.total_debt

        config = CascadeConfig(initial_debt_to_liquidate=100_000.0)
        simulate_cascade(pool_state, rate_params, config)

        assert pool_state.total_supply == original_supply
        assert pool_state.total_debt == original_debt

    def test_respects_max_steps(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            price_impact_per_unit=0.0001,
            depeg_sensitivity=0.50,
            max_steps=3,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) <= 3

    def test_single_step_when_no_sensitivity(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            depeg_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) == 1

    def test_total_debt_liquidated_correct(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=50_000.0,
            depeg_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        step_sum = sum(s.debt_liquidated for s in result.steps)
        assert result.total_debt_liquidated == pytest.approx(step_sum)

    def test_collateral_seized_includes_bonus_and_price(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        """Collateral seized = debt * (1 + bonus) / collateral_price."""
        collateral_price = 1.18
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            collateral_price=collateral_price,
            liquidation_bonus=0.05,
            depeg_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) == 1
        step = result.steps[0]
        expected = 100_000.0 * 1.05 / collateral_price
        assert step.collateral_seized == pytest.approx(expected)

    def test_cascade_reduces_debt(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=200_000.0,
            price_impact_per_unit=0.0001,
            depeg_sensitivity=0.20,
            max_steps=5,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        if result.steps:
            assert result.steps[-1].total_debt < pool_state.total_debt

    def test_supply_unchanged_after_liquidation(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        """In the WETH pool, supply stays the same after liquidation."""
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            depeg_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert result.steps[0].total_supply == pool_state.total_supply

    def test_utilization_drops_after_liquidation(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        """Liquidation repays debt -> utilization drops in the WETH pool."""
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            depeg_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert result.final_utilization < pool_state.utilization

    def test_small_debt_below_threshold_no_cascade(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=50.0,
            min_debt_threshold=100.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) == 0
        assert result.total_debt_liquidated == 0.0

    def test_price_impact_depresses_collateral_price(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        """Selling seized wstETH should lower the collateral price each step."""
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            collateral_price=1.18,
            price_impact_per_unit=0.000001,
            depeg_sensitivity=0.30,
            max_steps=5,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) > 1
        # Each step should have a lower collateral price
        for i in range(1, len(result.steps)):
            assert result.steps[i].collateral_price < result.steps[i - 1].collateral_price

    def test_cascade_propagates_with_price_impact(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        """With sufficient price impact and sensitivity, cascade should
        produce multiple steps."""
        config = CascadeConfig(
            initial_debt_to_liquidate=200_000.0,
            collateral_price=1.18,
            price_impact_per_unit=0.000001,
            depeg_sensitivity=0.30,
            max_steps=10,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) > 1

    def test_cascade_does_not_immediately_wipe_out_all_debt(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        """With moderate sensitivity, the cascade should produce multiple
        meaningful steps rather than liquidating all debt in step 2."""
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            collateral_price=1.18,
            price_impact_per_unit=0.000001,
            depeg_sensitivity=0.5,
            max_steps=10,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) >= 3
        # No single step should liquidate more than 50% of the original debt
        for step in result.steps:
            assert step.debt_liquidated < pool_state.total_debt * 0.5
        # Total debt liquidated should be a fraction (not total wipeout)
        assert result.total_debt_liquidated < pool_state.total_debt

    def test_peg_drop_clamped(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        """Even with extreme price_impact_per_unit, collateral_price stays
        above the floor (never goes negative)."""
        config = CascadeConfig(
            initial_debt_to_liquidate=200_000.0,
            collateral_price=1.18,
            price_impact_per_unit=0.01,  # extremely high
            depeg_sensitivity=5.0,
            max_steps=5,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        for step in result.steps:
            assert step.collateral_price >= 0.01
