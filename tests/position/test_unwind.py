"""Tests for the enhanced unwind cost estimation."""

import pytest

from src.position.unwind import (
    DEXPoolParams,
    compute_amm_price_impact,
    estimate_gas_cost,
    estimate_unwind_cost,
    estimate_unwind_cost_detailed,
)
from src.simulation.results import UnwindCostResult


class TestBackwardCompatibility:
    def test_simple_slippage(self) -> None:
        cost = estimate_unwind_cost(10_000.0, slippage_bps=10.0)
        assert cost == pytest.approx(10.0)

    def test_simple_slippage_default(self) -> None:
        cost = estimate_unwind_cost(10_000.0)
        assert cost == pytest.approx(10.0)

    def test_zero_debt(self) -> None:
        cost = estimate_unwind_cost(0.0, slippage_bps=50.0)
        assert cost == pytest.approx(0.0)


class TestAMMPriceImpact:
    def test_zero_trade(self) -> None:
        pool = DEXPoolParams()
        assert compute_amm_price_impact(0.0, pool) == 0.0

    def test_small_trade_low_impact(self) -> None:
        pool = DEXPoolParams(reserve_x=50_000.0, reserve_y=50_000.0, fee_bps=4.0)
        impact = compute_amm_price_impact(100.0, pool)
        assert 0 < impact < 0.01  # Less than 1% for small trade

    def test_large_trade_higher_impact(self) -> None:
        pool = DEXPoolParams(reserve_x=50_000.0, reserve_y=50_000.0, fee_bps=4.0)
        small_impact = compute_amm_price_impact(100.0, pool)
        large_impact = compute_amm_price_impact(10_000.0, pool)
        assert large_impact > small_impact

    def test_impact_increases_with_trade_size(self) -> None:
        pool = DEXPoolParams(reserve_x=50_000.0, reserve_y=50_000.0, fee_bps=4.0)
        prev_impact = 0.0
        for size in [100, 500, 1000, 5000, 10000]:
            impact = compute_amm_price_impact(float(size), pool)
            assert impact >= prev_impact
            prev_impact = impact

    def test_impact_nonnegative(self) -> None:
        pool = DEXPoolParams()
        for size in [1, 10, 100, 1000, 10000]:
            assert compute_amm_price_impact(float(size), pool) >= 0.0


class TestGasCost:
    def test_default_gas(self) -> None:
        cost = estimate_gas_cost()
        assert cost > 0
        assert cost < 0.1  # Should be a small amount of ETH

    def test_gas_scales_with_price(self) -> None:
        cost_low = estimate_gas_cost(gas_price_gwei=10.0)
        cost_high = estimate_gas_cost(gas_price_gwei=100.0)
        assert cost_high > cost_low


class TestDetailedUnwindCost:
    def test_returns_unwind_cost_result(self) -> None:
        result = estimate_unwind_cost_detailed(10_000.0)
        assert isinstance(result, UnwindCostResult)

    def test_without_pool_uses_linear(self) -> None:
        result = estimate_unwind_cost_detailed(10_000.0, slippage_bps=20.0)
        assert result.effective_slippage_bps == pytest.approx(20.0)
        assert result.slippage_cost == pytest.approx(20.0)  # 10000 * 20/10000

    def test_with_pool_uses_amm(self) -> None:
        pool = DEXPoolParams(reserve_x=50_000.0, reserve_y=50_000.0, fee_bps=4.0)
        result = estimate_unwind_cost_detailed(10_000.0, pool=pool)
        assert result.price_impact > 0
        assert result.slippage_cost > 0
        assert result.total_cost > result.slippage_cost  # gas adds to total

    def test_total_equals_sum(self) -> None:
        pool = DEXPoolParams()
        result = estimate_unwind_cost_detailed(10_000.0, pool=pool)
        assert result.total_cost == pytest.approx(result.slippage_cost + result.gas_cost)

    def test_larger_trade_more_expensive(self) -> None:
        pool = DEXPoolParams()
        small = estimate_unwind_cost_detailed(1_000.0, pool=pool)
        large = estimate_unwind_cost_detailed(20_000.0, pool=pool)
        assert large.slippage_cost > small.slippage_cost

    def test_curve_liquidity_preferred_over_pool(self) -> None:
        """When curve_liquidity is provided, it should be used over the pool model."""
        from unittest.mock import MagicMock

        from src.data.dex_liquidity import SwapQuote

        mock_curve = MagicMock()
        # Selling 10000 stETH on Curve yields 9950 ETH (50 ETH slippage)
        mock_curve.get_swap_output.return_value = SwapQuote(
            input_amount=10_000.0,
            output_amount=9_950.0,
            price_impact=0.005,
            source="curve",
        )

        # Give it a pool too — should be ignored in favor of curve
        pool = DEXPoolParams(reserve_x=50_000.0, reserve_y=50_000.0, fee_bps=4.0)
        result = estimate_unwind_cost_detailed(
            10_000.0, pool=pool, curve_liquidity=mock_curve,
        )

        # Slippage = 10000 - 9950 = 50 ETH
        assert result.slippage_cost == pytest.approx(50.0)
        assert result.price_impact == pytest.approx(0.005)
        mock_curve.get_swap_output.assert_called_once_with(10_000.0)

    def test_steth_trade_size_equals_debt(self) -> None:
        """Trade size on Curve should be ~debt_amount stETH (1:1 peg assumption)."""
        from unittest.mock import MagicMock

        from src.data.dex_liquidity import SwapQuote

        mock_curve = MagicMock()
        mock_curve.get_swap_output.return_value = SwapQuote(
            input_amount=5_000.0,
            output_amount=4_998.0,
            price_impact=0.0004,
            source="curve",
        )

        estimate_unwind_cost_detailed(5_000.0, curve_liquidity=mock_curve)

        # Should sell ~5000 stETH to get ~5000 ETH for 5000 WETH debt
        call_args = mock_curve.get_swap_output.call_args[0]
        assert call_args[0] == pytest.approx(5_000.0)
