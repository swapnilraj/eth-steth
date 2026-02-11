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
            rate_sensitivity=0.10,
            max_steps=3,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) <= 3

    def test_single_step_when_no_sensitivity(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            rate_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) == 1

    def test_total_debt_liquidated_correct(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=50_000.0,
            rate_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        step_sum = sum(s.debt_liquidated for s in result.steps)
        assert result.total_debt_liquidated == pytest.approx(step_sum)

    def test_collateral_seized_includes_bonus(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            liquidation_bonus=0.05,
            rate_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) == 1
        step = result.steps[0]
        expected = 100_000.0 * 1.05
        assert step.collateral_seized == pytest.approx(expected)

    def test_cascade_reduces_debt(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=200_000.0,
            rate_sensitivity=0.05,
            max_steps=5,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        # Final debt in the last step should be less than original
        if result.steps:
            assert result.steps[-1].total_debt < pool_state.total_debt

    def test_utilization_changes_after_cascade(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=100_000.0,
            rate_sensitivity=0.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        # After liquidation, utilization should change
        assert result.final_utilization != pytest.approx(pool_state.utilization)

    def test_small_debt_below_threshold_no_cascade(
        self, pool_state: PoolState, rate_params: InterestRateParams
    ) -> None:
        config = CascadeConfig(
            initial_debt_to_liquidate=50.0,  # Below default threshold of 100
            min_debt_threshold=100.0,
        )
        result = simulate_cascade(pool_state, rate_params, config)
        assert len(result.steps) == 0
        assert result.total_debt_liquidated == 0.0
