"""Tests for VaR and CVaR calculations."""

import numpy as np
import pytest

from src.simulation.monte_carlo import run_monte_carlo
from src.stress.var import VaRResult, compute_var, compute_var_from_scenarios


@pytest.fixture
def mc_result():
    return run_monte_carlo(
        u0=0.44,
        collateral_value=14160.0,
        debt_value=10500.0,
        liquidation_threshold=0.955,
        staking_apy=0.035,
        n_paths=500,
        horizon_days=365,
        seed=42,
    )


class TestComputeVar:
    def test_result_type(self, mc_result) -> None:
        var = compute_var(mc_result)
        assert isinstance(var, VaRResult)

    def test_var99_leq_var95(self, mc_result) -> None:
        """VaR99 should be at least as bad as VaR95 (more extreme tail)."""
        var = compute_var(mc_result)
        assert var.var_99 <= var.var_95

    def test_cvar_leq_var(self, mc_result) -> None:
        """CVaR (expected shortfall) should be at least as bad as VaR."""
        var = compute_var(mc_result)
        assert var.cvar_95 <= var.var_95
        assert var.cvar_99 <= var.var_99

    def test_max_loss_leq_var99(self, mc_result) -> None:
        var = compute_var(mc_result)
        assert var.max_loss <= var.var_99

    def test_liquidation_prob_in_range(self, mc_result) -> None:
        var = compute_var(mc_result)
        assert 0.0 <= var.liquidation_prob <= 1.0


class TestComputeVarFromScenarios:
    def test_basic_computation(self) -> None:
        pnl = np.array([-100, -50, -20, -10, 0, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100.0] * 10)
        var = compute_var_from_scenarios(pnl)
        assert isinstance(var, VaRResult)
        assert var.var_99 <= var.var_95
        assert var.max_loss == -100.0

    def test_all_positive(self) -> None:
        pnl = np.ones(100) * 50.0
        var = compute_var_from_scenarios(pnl)
        assert var.var_95 == pytest.approx(50.0)
        assert var.var_99 == pytest.approx(50.0)

    def test_all_negative(self) -> None:
        pnl = np.linspace(-200, -100, 100)
        var = compute_var_from_scenarios(pnl)
        assert var.var_95 < 0
        assert var.var_99 < 0
        assert var.cvar_99 <= var.var_99

    def test_cvar_worse_than_var(self) -> None:
        rng = np.random.default_rng(42)
        pnl = rng.normal(-10, 50, size=1000)
        var = compute_var_from_scenarios(pnl)
        assert var.cvar_95 <= var.var_95
        assert var.cvar_99 <= var.var_99

    def test_liquidation_prob_zero_without_arrays(self) -> None:
        """Without stressed collateral/debt arrays, liquidation prob should be 0."""
        pnl = np.array([-1000.0] * 100)  # severe losses
        var = compute_var_from_scenarios(
            pnl,
            collateral_value=14000.0,
            debt_value=10000.0,
        )
        # No arrays provided → no HF computation → 0 liquidation prob
        assert var.liquidation_prob == 0.0

    def test_liquidation_prob_with_arrays(self) -> None:
        """With explicit arrays, liquidation prob should reflect HF < 1.0."""
        n = 100
        pnl = np.zeros(n)
        # Half the scenarios have HF < 1.0, half have HF > 1.0
        stressed_coll = np.full(n, 10000.0)
        # Safe half: debt=9000 → HF = (10000 * 0.955) / 9000 ≈ 1.061 > 1.0
        stressed_debt = np.full(n, 9000.0)
        # Liquidated half: debt=12000 → HF = (10000 * 0.955) / 12000 ≈ 0.796 < 1.0
        stressed_debt[:50] = 12000.0
        var = compute_var_from_scenarios(
            pnl,
            collateral_value=10000.0,
            debt_value=10000.0,
            liquidation_threshold=0.955,
            stressed_collateral_array=stressed_coll,
            stressed_debt_array=stressed_debt,
        )
        assert var.liquidation_prob == pytest.approx(0.5)
