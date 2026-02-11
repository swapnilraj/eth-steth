"""Monte Carlo simulation engine for utilization paths and P&L."""

from dataclasses import dataclass

import numpy as np

from src.simulation.results import MonteCarloResult


@dataclass(frozen=True)
class OUParams:
    """Parameters for the Ornstein-Uhlenbeck utilization process.

    Attributes:
        theta: Long-run mean utilization.
        kappa: Mean-reversion speed (higher = faster revert).
        sigma: Volatility of utilization shocks.
    """

    theta: float = 0.44
    kappa: float = 5.0
    sigma: float = 0.08


def simulate_utilization_paths(
    ou: OUParams,
    u0: float,
    n_paths: int,
    n_steps: int,
    dt: float,
    rng: np.random.Generator,
) -> np.ndarray:
    """Simulate utilization paths via Euler-Maruyama on an OU process.

    Args:
        ou: OU process parameters.
        u0: Initial utilization.
        n_paths: Number of Monte Carlo paths.
        n_steps: Number of time steps.
        dt: Time step size in years (e.g. 1/365).
        rng: Numpy random generator for reproducibility.

    Returns:
        (n_paths, n_steps) array of utilization values clamped to [0, 1].
    """
    paths = np.empty((n_paths, n_steps))
    paths[:, 0] = u0

    sqrt_dt = np.sqrt(dt)
    noise = rng.standard_normal((n_paths, n_steps - 1))

    for t in range(1, n_steps):
        drift = ou.kappa * (ou.theta - paths[:, t - 1]) * dt
        diffusion = ou.sigma * sqrt_dt * noise[:, t - 1]
        paths[:, t] = paths[:, t - 1] + drift + diffusion

    # Clamp to [0, 1]
    np.clip(paths, 0.0, 1.0, out=paths)
    return paths


def _vectorized_borrow_rate(
    utilization: np.ndarray,
    optimal_utilization: float,
    base_rate: float,
    slope1: float,
    slope2: float,
) -> np.ndarray:
    """Vectorized piecewise borrow rate computation.

    Matches InterestRateModel.variable_borrow_rate but works on arrays.
    """
    below_kink = utilization <= optimal_utilization
    rate = np.where(
        below_kink,
        base_rate + (utilization / optimal_utilization) * slope1,
        base_rate
        + slope1
        + ((utilization - optimal_utilization) / (1.0 - optimal_utilization)) * slope2,
    )
    return rate


def run_monte_carlo(
    u0: float,
    collateral_value: float,
    debt_value: float,
    liquidation_threshold: float,
    staking_apy: float,
    optimal_utilization: float = 0.92,
    base_rate: float = 0.0,
    slope1: float = 0.027,
    slope2: float = 0.40,
    ou_params: OUParams | None = None,
    n_paths: int = 1000,
    horizon_days: int = 365,
    seed: int | None = None,
) -> MonteCarloResult:
    """Run a full Monte Carlo simulation of borrow rates and P&L.

    Args:
        u0: Initial WETH utilization.
        collateral_value: Collateral value in ETH.
        debt_value: Debt value in ETH.
        liquidation_threshold: Liquidation threshold (e.g. 0.955 for E-mode).
        staking_apy: Annual staking yield.
        optimal_utilization: Kink point for rate curve.
        base_rate: Base borrow rate.
        slope1: Slope below kink.
        slope2: Slope above kink.
        ou_params: OU process parameters (defaults used if None).
        n_paths: Number of simulation paths.
        horizon_days: Simulation horizon in days.
        seed: Random seed for reproducibility.

    Returns:
        MonteCarloResult with all path data.
    """
    if ou_params is None:
        ou_params = OUParams()

    rng = np.random.default_rng(seed)
    dt = 1.0 / 365.0
    n_steps = horizon_days

    # Simulate utilization
    util_paths = simulate_utilization_paths(
        ou_params, u0, n_paths, n_steps, dt, rng
    )

    # Vectorized rate computation
    rate_paths = _vectorized_borrow_rate(
        util_paths, optimal_utilization, base_rate, slope1, slope2
    )

    # P&L tracking: daily income - daily cost, accumulated
    # Income per day = collateral_value * staking_apy / 365
    # Cost per day = debt_value * borrow_rate / 365
    daily_income = collateral_value * staking_apy / 365.0
    daily_cost = debt_value * rate_paths / 365.0  # (n_paths, n_steps)
    daily_pnl = daily_income - daily_cost

    pnl_paths = np.cumsum(daily_pnl, axis=1)
    terminal_pnl = pnl_paths[:, -1]

    # Liquidation detection: check if cumulative losses erode equity enough
    # that HF drops below 1.0
    equity = collateral_value - debt_value
    # HF = (collateral_value * liq_threshold) / (debt_value)
    # As P&L erodes equity, effective collateral drops
    # Simplified: liquidation when cumulative P&L < -(equity - debt_value * (1 - 1/liq_threshold))
    # i.e., when collateral_value + pnl < debt_value / liq_threshold
    liq_threshold_value = debt_value / liquidation_threshold
    liq_pnl_threshold = -(collateral_value - liq_threshold_value)
    liquidated = np.any(pnl_paths <= liq_pnl_threshold, axis=1)

    timesteps = np.arange(n_steps, dtype=float)

    return MonteCarloResult(
        utilization_paths=util_paths,
        rate_paths=rate_paths,
        pnl_paths=pnl_paths,
        terminal_pnl=terminal_pnl,
        liquidated=liquidated,
        timesteps=timesteps,
    )
