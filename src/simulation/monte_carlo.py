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

    theta: float = 0.78
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
    supply_apy: float = 0.0,
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

    Models Aave mechanics faithfully:
    - Collateral value grows with staking + supply APY
    - Debt balance grows with accrued borrow interest
    - HF = (collateral * liq_threshold) / debt, checked each step

    Args:
        u0: Initial WETH utilization.
        collateral_value: Collateral value in ETH.
        debt_value: Debt value in ETH.
        liquidation_threshold: Liquidation threshold (e.g. 0.955 for E-mode).
        staking_apy: Annual staking yield.
        supply_apy: Annual Aave supply yield on wstETH collateral.
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

    # Track collateral and debt balances per path (Aave mechanics):
    # - Collateral accrues staking + supply yield daily
    # - Debt accrues borrow interest daily (variable debt tokens grow)
    collateral_paths = np.empty((n_paths, n_steps))
    debt_paths = np.empty((n_paths, n_steps))
    collateral_paths[:, 0] = collateral_value
    debt_paths[:, 0] = debt_value

    daily_income_rate = (staking_apy + supply_apy) / 365.0
    for t in range(1, n_steps):
        # Collateral grows with staking + supply yield
        collateral_paths[:, t] = collateral_paths[:, t - 1] * (1.0 + daily_income_rate)
        # Debt grows with accrued borrow interest
        daily_borrow_rate = rate_paths[:, t - 1] / 365.0
        debt_paths[:, t] = debt_paths[:, t - 1] * (1.0 + daily_borrow_rate)

    # P&L = equity change from initial
    equity_paths = collateral_paths - debt_paths
    initial_equity = collateral_value - debt_value
    pnl_paths = equity_paths - initial_equity
    terminal_pnl = pnl_paths[:, -1]

    # Liquidation detection: HF = (collateral * liq_threshold) / debt < 1.0
    hf_paths = (collateral_paths * liquidation_threshold) / debt_paths
    liquidated = np.any(hf_paths < 1.0, axis=1)

    timesteps = np.arange(n_steps, dtype=float)

    return MonteCarloResult(
        utilization_paths=util_paths,
        rate_paths=rate_paths,
        pnl_paths=pnl_paths,
        terminal_pnl=terminal_pnl,
        liquidated=liquidated,
        timesteps=timesteps,
    )
