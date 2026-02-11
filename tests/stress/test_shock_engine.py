"""Tests for the shock engine."""

import numpy as np
import pytest

from src.stress.scenarios import JUNE_2022_DEPEG, create_custom_scenario
from src.stress.shock_engine import (
    CorrelationMatrix,
    ShockResult,
    apply_scenario,
    generate_correlated_scenarios,
)


class TestApplyScenario:
    def test_depeg_reduces_hf(self) -> None:
        result = apply_scenario(
            scenario=JUNE_2022_DEPEG,
            collateral_amount=12_000.0,
            collateral_price=1.18,
            debt_value=10_500.0,
            liquidation_threshold=0.955,
        )
        assert result.hf_after < result.hf_before

    def test_no_change_preserves_hf(self) -> None:
        no_stress = create_custom_scenario(
            name="No stress",
            eth_price_change=0.0,
            steth_peg=1.0,
            utilization_shock=0.44,
        )
        result = apply_scenario(
            scenario=no_stress,
            collateral_amount=12_000.0,
            collateral_price=1.18,
            debt_value=10_500.0,
            liquidation_threshold=0.955,
        )
        assert result.hf_before == pytest.approx(result.hf_after, rel=1e-6)

    def test_severe_depeg_triggers_liquidation(self) -> None:
        # In an ETH-denominated position, only the peg matters for HF.
        # A peg of 0.75 on 12k wstETH at 1.18 with 10.5k debt:
        # HF = (12000 * 1.18 * 0.75 * 0.955) / 10500 ≈ 0.966 < 1.0
        severe = create_custom_scenario(
            name="Severe",
            eth_price_change=-0.60,  # ignored for ETH-denominated position
            steth_peg=0.75,
            utilization_shock=0.99,
        )
        result = apply_scenario(
            scenario=severe,
            collateral_amount=12_000.0,
            collateral_price=1.18,
            debt_value=10_500.0,
            liquidation_threshold=0.955,
        )
        assert result.is_liquidated is True
        assert result.hf_after < 1.0

    def test_pnl_impact_negative_for_crash(self) -> None:
        result = apply_scenario(
            scenario=JUNE_2022_DEPEG,
            collateral_amount=12_000.0,
            collateral_price=1.18,
            debt_value=10_500.0,
            liquidation_threshold=0.955,
        )
        assert result.pnl_impact < 0

    def test_result_is_shock_result(self) -> None:
        result = apply_scenario(
            scenario=JUNE_2022_DEPEG,
            collateral_amount=12_000.0,
            collateral_price=1.18,
            debt_value=10_500.0,
            liquidation_threshold=0.955,
        )
        assert isinstance(result, ShockResult)


class TestCorrelatedScenarios:
    def test_shape(self) -> None:
        result = generate_correlated_scenarios(n_scenarios=100, seed=42)
        assert result.shape == (100, 3)

    def test_peg_bounded(self) -> None:
        result = generate_correlated_scenarios(n_scenarios=1000, seed=42)
        assert np.all(result[:, 1] > 0)
        assert np.all(result[:, 1] <= 1.0)

    def test_utilization_bounded(self) -> None:
        result = generate_correlated_scenarios(n_scenarios=1000, seed=42)
        assert np.all(result[:, 2] >= 0.0)
        assert np.all(result[:, 2] <= 1.0)

    def test_deterministic_with_seed(self) -> None:
        r1 = generate_correlated_scenarios(n_scenarios=50, seed=99)
        r2 = generate_correlated_scenarios(n_scenarios=50, seed=99)
        np.testing.assert_array_equal(r1, r2)

    def test_correlation_structure(self) -> None:
        """ETH price drops should correlate with peg drops."""
        result = generate_correlated_scenarios(n_scenarios=5000, seed=42)
        # Peg shocks centred around base_peg (default 1.0)
        corr = np.corrcoef(result[:, 0], result[:, 1] - 1.0)[0, 1]
        # Should be positively correlated (both drop together)
        assert corr > 0.3

    def test_base_peg_shifts_distribution(self) -> None:
        """Scenarios should centre around the supplied base_peg."""
        result = generate_correlated_scenarios(
            n_scenarios=5000, base_peg=0.95, seed=42
        )
        mean_peg = float(np.mean(result[:, 1]))
        # Mean should be close to 0.95, not 1.0
        assert abs(mean_peg - 0.95) < 0.03

    def test_base_utilization_shifts_distribution(self) -> None:
        """Scenarios should centre around the supplied base_utilization."""
        result = generate_correlated_scenarios(
            n_scenarios=5000, base_utilization=0.90, seed=42
        )
        mean_util = float(np.mean(result[:, 2]))
        assert abs(mean_util - 0.90) < 0.05

    def test_custom_correlation_matrix(self) -> None:
        custom = CorrelationMatrix(
            matrix=np.array([
                [1.0, 0.9, -0.1],
                [0.9, 1.0, -0.1],
                [-0.1, -0.1, 1.0],
            ])
        )
        result = generate_correlated_scenarios(
            n_scenarios=100, correlation=custom, seed=42
        )
        assert result.shape == (100, 3)
