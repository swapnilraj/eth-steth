"""Shock engine — apply stress scenarios and generate correlated shocks."""

from dataclasses import dataclass, field

import numpy as np

from src.stress.scenarios import StressScenario


@dataclass(frozen=True)
class ShockResult:
    """Result of applying a stress scenario to a position."""

    hf_before: float
    hf_after: float
    collateral_before: float
    collateral_after: float
    pnl_impact: float
    is_liquidated: bool


@dataclass(frozen=True)
class CorrelationMatrix:
    """Default correlations between ETH price, stETH peg, and utilization.

    Matrix order: [eth_price_change, steth_peg_change, utilization_change]
    """

    matrix: np.ndarray = field(
        default_factory=lambda: np.array(
            [
                [1.0, 0.6, -0.5],
                [0.6, 1.0, -0.3],
                [-0.5, -0.3, 1.0],
            ]
        )
    )


def apply_scenario(
    scenario: StressScenario,
    collateral_amount: float,
    collateral_price: float,
    debt_value: float,
    liquidation_threshold: float,
    current_peg: float = 1.0,
) -> ShockResult:
    """Apply a stress scenario to a position and compute impact.

    Args:
        scenario: The stress scenario to apply.
        collateral_amount: wstETH collateral amount.
        collateral_price: wstETH/ETH price.
        debt_value: Total debt in ETH.
        liquidation_threshold: Liquidation threshold (e.g. 0.955).
        current_peg: Current stETH/ETH peg.

    Returns:
        ShockResult with before/after health factors and P&L impact.
    """
    collateral_before = collateral_amount * collateral_price * current_peg
    hf_before = (collateral_before * liquidation_threshold) / debt_value if debt_value > 0 else float("inf")

    # Apply stress: only the peg matters for an ETH-denominated position.
    # A USD move in ETH affects both collateral and debt equally (both are
    # in ETH), so the health factor is unchanged. The only risk factor is
    # the stETH/ETH peg deviation.
    collateral_after = collateral_amount * collateral_price * scenario.steth_peg

    hf_after = (collateral_after * liquidation_threshold) / debt_value if debt_value > 0 else float("inf")

    pnl_impact = collateral_after - collateral_before

    return ShockResult(
        hf_before=hf_before,
        hf_after=hf_after,
        collateral_before=collateral_before,
        collateral_after=collateral_after,
        pnl_impact=pnl_impact,
        is_liquidated=hf_after < 1.0,
    )


def generate_correlated_scenarios(
    n_scenarios: int,
    base_peg: float = 1.0,
    base_utilization: float = 0.78,
    eth_vol: float = 0.30,
    peg_vol: float = 0.05,
    util_vol: float = 0.10,
    correlation: CorrelationMatrix | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """Generate correlated shock vectors using Cholesky decomposition.

    Args:
        n_scenarios: Number of correlated scenarios to generate.
        base_peg: Current stETH/ETH peg to centre shocks around.
        base_utilization: Current WETH utilization to centre shocks around.
        eth_vol: Annualized ETH price volatility.
        peg_vol: stETH peg deviation volatility.
        util_vol: Utilization shock volatility.
        correlation: Correlation matrix (uses default if None).
        seed: Random seed for reproducibility.

    Returns:
        (n_scenarios, 3) array with columns:
        [eth_price_change, steth_peg, utilization_shock]
    """
    if correlation is None:
        correlation = CorrelationMatrix()

    rng = np.random.default_rng(seed)

    # Build covariance from correlation + volatilities
    vols = np.array([eth_vol, peg_vol, util_vol])
    cov = correlation.matrix * np.outer(vols, vols)

    # Cholesky decomposition
    L = np.linalg.cholesky(cov)

    # Generate independent standard normal samples
    z = rng.standard_normal((n_scenarios, 3))

    # Transform to correlated shocks
    shocks = z @ L.T

    # Post-process:
    # eth_price_change: raw (can be negative)
    # steth_peg: base_peg + peg_shock, clamped to (0, 1]
    # utilization_shock: base_utilization + util_shock, clamped to [0, 1]
    result = np.empty_like(shocks)
    result[:, 0] = shocks[:, 0]  # ETH price change (fractional)
    result[:, 1] = np.clip(base_peg + shocks[:, 1], 0.01, 1.0)  # peg ratio
    result[:, 2] = np.clip(base_utilization + shocks[:, 2], 0.0, 1.0)  # utilization level

    return result
