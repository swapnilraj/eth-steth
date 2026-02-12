"""Monte Carlo simulation engine for utilization paths and P&L.

Models two correlated stochastic factors:
1. WETH utilization — Ornstein-Uhlenbeck mean-reverting process
2. wstETH/ETH exchange rate — Jump-diffusion (GBM + Poisson slashing)

The exchange rate dynamics capture both continuous peg volatility and
discrete Lido slashing events, correlated with utilization via Cholesky
decomposition.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.simulation.params import PegDynamicsParams  # noqa: F401 — re-exported
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


def _simulate_correlated_paths(
    ou: OUParams,
    peg_params: PegDynamicsParams,
    u0: float,
    peg0: float,
    staking_apy: float,
    n_paths: int,
    n_steps: int,
    dt: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Simulate correlated utilization and peg paths.

    Uses Cholesky decomposition to correlate the Brownian motions driving
    utilization and exchange rate dynamics.

    Returns:
        (util_paths, peg_paths) each of shape (n_paths, n_steps).
    """
    rho = peg_params.peg_util_correlation

    # Cholesky factor for 2×2 correlation matrix [[1, ρ], [ρ, 1]]
    # L = [[1, 0], [ρ, sqrt(1-ρ²)]]
    sqrt_one_minus_rho2 = np.sqrt(max(0.0, 1.0 - rho * rho))

    sqrt_dt = np.sqrt(dt)

    # Generate independent normals: (2, n_paths, n_steps-1)
    z = rng.standard_normal((2, n_paths, n_steps - 1))

    # Apply Cholesky: dW_util = z[0], dW_peg = ρ·z[0] + sqrt(1-ρ²)·z[1]
    dw_util = z[0]
    dw_peg = rho * z[0] + sqrt_one_minus_rho2 * z[1]

    # Poisson jumps for slashing events
    jump_prob_per_step = peg_params.peg_jump_intensity * dt
    jumps = rng.binomial(1, jump_prob_per_step, (n_paths, n_steps - 1))

    # --- Utilization paths (OU process) ---
    util_paths = np.empty((n_paths, n_steps))
    util_paths[:, 0] = u0

    for t in range(1, n_steps):
        drift = ou.kappa * (ou.theta - util_paths[:, t - 1]) * dt
        diffusion = ou.sigma * sqrt_dt * dw_util[:, t - 1]
        util_paths[:, t] = util_paths[:, t - 1] + drift + diffusion

    np.clip(util_paths, 0.0, 1.0, out=util_paths)

    # --- Peg paths (GBM + jumps) ---
    peg_paths = np.empty((n_paths, n_steps))
    peg_paths[:, 0] = peg0

    sigma = peg_params.peg_vol
    mu = staking_apy  # Drift from staking rewards

    for t in range(1, n_steps):
        # GBM increment: S(t) = S(t-1) * exp((μ - σ²/2)dt + σ√dt·dW)
        log_return = (mu - 0.5 * sigma * sigma) * dt + sigma * sqrt_dt * dw_peg[:, t - 1]

        # Jump component: multiplicative shock (1 + jump_size) when jump occurs
        jump_factor = 1.0 + peg_params.peg_jump_size * jumps[:, t - 1]

        peg_paths[:, t] = peg_paths[:, t - 1] * np.exp(log_return) * jump_factor

    # Floor at 0.01 for numerical stability
    np.clip(peg_paths, 0.01, None, out=peg_paths)

    return util_paths, peg_paths


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
    peg_params: PegDynamicsParams | None = None,
    initial_peg: float = 1.0,
) -> MonteCarloResult:
    """Run a full Monte Carlo simulation of borrow rates and P&L.

    Models two correlated stochastic factors:
    1. WETH utilization (OU process) → borrow rate → debt growth
    2. wstETH/ETH exchange rate (jump-diffusion) → collateral value

    When peg_params is None, the exchange rate is held constant (backward
    compatible with the original utilization-only model).

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
        peg_params: Exchange rate dynamics parameters. None = fixed peg.
        initial_peg: Starting exchange rate (1.0 = perfect peg).

    Returns:
        MonteCarloResult with all path data including peg paths.
    """
    if ou_params is None:
        ou_params = OUParams()

    rng = np.random.default_rng(seed)
    dt = 1.0 / 365.0
    n_steps = horizon_days + 1  # +1: index 0 = initial state

    # --- Simulate stochastic factors ---
    if peg_params is not None:
        # Correlated utilization + peg paths
        util_paths, peg_paths = _simulate_correlated_paths(
            ou=ou_params,
            peg_params=peg_params,
            u0=u0,
            peg0=initial_peg,
            staking_apy=staking_apy,
            n_paths=n_paths,
            n_steps=n_steps,
            dt=dt,
            rng=rng,
        )
    else:
        # Backward compatible: utilization only, fixed peg
        util_paths = simulate_utilization_paths(
            ou_params, u0, n_paths, n_steps, dt, rng
        )
        peg_paths = None

    # Vectorized rate computation
    rate_paths = _vectorized_borrow_rate(
        util_paths, optimal_utilization, base_rate, slope1, slope2
    )

    # --- Track collateral and debt balances ---
    collateral_paths = np.empty((n_paths, n_steps))
    debt_paths = np.empty((n_paths, n_steps))
    collateral_paths[:, 0] = collateral_value
    debt_paths[:, 0] = debt_value

    daily_income_rate = (staking_apy + supply_apy) / 365.0

    if peg_paths is not None:
        # Peg-adjusted collateral: value changes with exchange rate
        # The staking APY drift is already embedded in the peg path (GBM drift),
        # so we only add supply APY as additional income on collateral.
        daily_supply_rate = supply_apy / 365.0
        # Collateral value at each step = base_collateral × (peg[t] / peg[0]) + supply income
        # We track the "amount" growing with supply income, then multiply by peg ratio
        collateral_amount_paths = np.empty((n_paths, n_steps))
        collateral_amount_paths[:, 0] = collateral_value / initial_peg if initial_peg > 0 else collateral_value

        for t in range(1, n_steps):
            # Amount grows with supply yield only (staking is in peg drift)
            collateral_amount_paths[:, t] = collateral_amount_paths[:, t - 1] * (1.0 + daily_supply_rate)
            # Value = amount × peg
            collateral_paths[:, t] = collateral_amount_paths[:, t] * peg_paths[:, t]
            # Debt grows with borrow interest
            daily_borrow_rate = rate_paths[:, t - 1] / 365.0
            debt_paths[:, t] = debt_paths[:, t - 1] * (1.0 + daily_borrow_rate)

        # Fix initial collateral value
        collateral_paths[:, 0] = collateral_value
    else:
        # Original model: fixed peg, collateral grows with staking + supply
        for t in range(1, n_steps):
            collateral_paths[:, t] = collateral_paths[:, t - 1] * (1.0 + daily_income_rate)
            daily_borrow_rate = rate_paths[:, t - 1] / 365.0
            debt_paths[:, t] = debt_paths[:, t - 1] * (1.0 + daily_borrow_rate)

    # --- Liquidation detection ---
    hf_paths = (collateral_paths * liquidation_threshold) / debt_paths
    liquidated = np.any(hf_paths < 1.0, axis=1)

    # Freeze balances at first liquidation timestep
    if np.any(liquidated):
        hf_below = hf_paths < 1.0
        first_liq_step = np.argmax(hf_below, axis=1)
        liq_indices = np.where(liquidated)[0]
        for i in liq_indices:
            t = first_liq_step[i]
            collateral_paths[i, t:] = collateral_paths[i, t]
            debt_paths[i, t:] = debt_paths[i, t]
            if peg_paths is not None:
                peg_paths[i, t:] = peg_paths[i, t]
        # Recompute HF from frozen paths
        hf_paths = (collateral_paths * liquidation_threshold) / debt_paths

    # P&L = equity change from initial
    equity_paths = collateral_paths - debt_paths
    initial_equity = collateral_value - debt_value
    pnl_paths = equity_paths - initial_equity
    terminal_pnl = pnl_paths[:, -1]

    timesteps = np.arange(n_steps, dtype=float)

    return MonteCarloResult(
        utilization_paths=util_paths,
        rate_paths=rate_paths,
        pnl_paths=pnl_paths,
        terminal_pnl=terminal_pnl,
        liquidated=liquidated,
        hf_paths=hf_paths,
        timesteps=timesteps,
        peg_paths=peg_paths,
        collateral_value_paths=collateral_paths,
    )
