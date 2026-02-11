"""Tests for the Monte Carlo simulation engine."""

import numpy as np
import pytest

from src.simulation.monte_carlo import (
    OUParams,
    _vectorized_borrow_rate,
    run_monte_carlo,
    simulate_utilization_paths,
)


class TestOUProcess:
    def test_paths_bounded_0_1(self) -> None:
        ou = OUParams(theta=0.5, kappa=5.0, sigma=0.15)
        rng = np.random.default_rng(42)
        paths = simulate_utilization_paths(ou, 0.5, n_paths=500, n_steps=365, dt=1 / 365, rng=rng)
        assert np.all(paths >= 0.0)
        assert np.all(paths <= 1.0)

    def test_mean_reverts_to_theta(self) -> None:
        ou = OUParams(theta=0.60, kappa=10.0, sigma=0.05)
        rng = np.random.default_rng(123)
        paths = simulate_utilization_paths(ou, 0.30, n_paths=2000, n_steps=365, dt=1 / 365, rng=rng)
        # After 1 year with strong mean reversion, mean should be near theta
        final_mean = np.mean(paths[:, -1])
        assert abs(final_mean - 0.60) < 0.05

    def test_deterministic_with_seed(self) -> None:
        ou = OUParams()
        rng1 = np.random.default_rng(99)
        rng2 = np.random.default_rng(99)
        p1 = simulate_utilization_paths(ou, 0.44, 100, 50, 1 / 365, rng1)
        p2 = simulate_utilization_paths(ou, 0.44, 100, 50, 1 / 365, rng2)
        np.testing.assert_array_equal(p1, p2)

    def test_shape(self) -> None:
        ou = OUParams()
        rng = np.random.default_rng(0)
        paths = simulate_utilization_paths(ou, 0.5, n_paths=10, n_steps=30, dt=1 / 365, rng=rng)
        assert paths.shape == (10, 30)

    def test_initial_value(self) -> None:
        ou = OUParams()
        rng = np.random.default_rng(0)
        paths = simulate_utilization_paths(ou, 0.75, n_paths=5, n_steps=10, dt=1 / 365, rng=rng)
        np.testing.assert_array_almost_equal(paths[:, 0], 0.75)


class TestVectorizedBorrowRate:
    def test_matches_scalar(self) -> None:
        from src.protocol.interest_rate import InterestRateModel, InterestRateParams

        params = InterestRateParams(
            optimal_utilization=0.92, base_rate=0.0, slope1=0.027, slope2=0.40, reserve_factor=0.15
        )
        model = InterestRateModel(params)

        utils = np.array([0.0, 0.46, 0.92, 0.96, 1.0])
        vec_rates = _vectorized_borrow_rate(utils, 0.92, 0.0, 0.027, 0.40)
        scalar_rates = np.array([model.variable_borrow_rate(u) for u in utils])
        np.testing.assert_array_almost_equal(vec_rates, scalar_rates)


class TestRunMonteCarlo:
    def test_result_shapes(self) -> None:
        mc = run_monte_carlo(
            u0=0.44,
            collateral_value=14160.0,
            debt_value=10500.0,
            liquidation_threshold=0.955,
            staking_apy=0.035,
            n_paths=50,
            horizon_days=30,
            seed=42,
        )
        assert mc.utilization_paths.shape == (50, 30)
        assert mc.rate_paths.shape == (50, 30)
        assert mc.pnl_paths.shape == (50, 30)
        assert mc.terminal_pnl.shape == (50,)
        assert mc.liquidated.shape == (50,)
        assert mc.hf_paths.shape == (50, 30)
        assert mc.timesteps.shape == (30,)

    def test_deterministic(self) -> None:
        kwargs = dict(
            u0=0.44,
            collateral_value=14160.0,
            debt_value=10500.0,
            liquidation_threshold=0.955,
            staking_apy=0.035,
            n_paths=20,
            horizon_days=30,
            seed=42,
        )
        mc1 = run_monte_carlo(**kwargs)
        mc2 = run_monte_carlo(**kwargs)
        np.testing.assert_array_equal(mc1.terminal_pnl, mc2.terminal_pnl)

    def test_utilization_bounded(self) -> None:
        mc = run_monte_carlo(
            u0=0.44,
            collateral_value=14160.0,
            debt_value=10500.0,
            liquidation_threshold=0.955,
            staking_apy=0.035,
            n_paths=100,
            horizon_days=365,
            seed=7,
        )
        assert np.all(mc.utilization_paths >= 0.0)
        assert np.all(mc.utilization_paths <= 1.0)

    def test_liquidated_is_boolean(self) -> None:
        mc = run_monte_carlo(
            u0=0.44,
            collateral_value=14160.0,
            debt_value=10500.0,
            liquidation_threshold=0.955,
            staking_apy=0.035,
            n_paths=20,
            horizon_days=30,
            seed=42,
        )
        assert mc.liquidated.dtype == bool

    def test_liquidated_paths_frozen_after_breach(self) -> None:
        """Once HF < 1.0, balances should not keep changing."""
        # Use very high utilization to force some liquidations
        mc = run_monte_carlo(
            u0=0.96,
            collateral_value=11000.0,
            debt_value=10500.0,
            liquidation_threshold=0.955,
            staking_apy=0.035,
            ou_params=OUParams(theta=0.96, kappa=10.0, sigma=0.02),
            n_paths=500,
            horizon_days=365,
            seed=42,
        )
        if not np.any(mc.liquidated):
            pytest.skip("No liquidations occurred — adjust test parameters")
        # For liquidated paths, P&L should be constant after the breach
        liq_indices = np.where(mc.liquidated)[0]
        hf_below = mc.hf_paths < 1.0
        first_liq_step = np.argmax(hf_below, axis=1)
        for i in liq_indices:
            t = first_liq_step[i]
            if t < mc.pnl_paths.shape[1] - 1:
                # All post-liquidation P&L values should be identical
                post_liq_pnl = mc.pnl_paths[i, t:]
                assert np.all(post_liq_pnl == post_liq_pnl[0]), (
                    f"Path {i}: P&L changed after liquidation at step {t}"
                )

    def test_high_utilization_more_costly(self) -> None:
        """Higher starting utilization should generally lead to worse P&L."""
        mc_low = run_monte_carlo(
            u0=0.30,
            collateral_value=14160.0,
            debt_value=10500.0,
            liquidation_threshold=0.955,
            staking_apy=0.035,
            ou_params=OUParams(theta=0.30, kappa=10.0, sigma=0.02),
            n_paths=500,
            horizon_days=365,
            seed=42,
        )
        mc_high = run_monte_carlo(
            u0=0.95,
            collateral_value=14160.0,
            debt_value=10500.0,
            liquidation_threshold=0.955,
            staking_apy=0.035,
            ou_params=OUParams(theta=0.95, kappa=10.0, sigma=0.02),
            n_paths=500,
            horizon_days=365,
            seed=42,
        )
        assert np.mean(mc_low.terminal_pnl) > np.mean(mc_high.terminal_pnl)
