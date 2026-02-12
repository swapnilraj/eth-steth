"""Parameters for exchange rate dynamics in Monte Carlo simulations."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class PegDynamicsParams:
    """Parameters for wstETH/ETH exchange rate jump-diffusion process.

    The exchange rate follows:
      dS/S = (staking_apy - 0.5σ²)dt + σ·dW + J·dN

    where dW is a Brownian motion correlated with utilization shocks,
    J is the jump size, and dN is a Poisson process with intensity λ.

    Attributes:
        peg_vol: Annualized volatility of the exchange rate (σ).
        peg_jump_intensity: Average number of jump events per year (λ).
        peg_jump_size: Mean fractional jump size (negative = slashing).
        peg_util_correlation: Correlation between peg shocks and utilization (ρ).
    """

    peg_vol: float = 0.03
    peg_jump_intensity: float = 0.1
    peg_jump_size: float = -0.05
    peg_util_correlation: float = -0.5


def calibrate_peg_params(
    daily_peg_values: list[float],
    min_observations: int = 30,
) -> PegDynamicsParams:
    """Calibrate peg dynamics parameters from historical daily peg values.

    Args:
        daily_peg_values: Chronological list of daily stETH/ETH peg values.
        min_observations: Minimum number of observations required.

    Returns:
        Calibrated PegDynamicsParams.
    """
    if len(daily_peg_values) < min_observations:
        return PegDynamicsParams()  # Return defaults

    prices = np.array(daily_peg_values)
    log_returns = np.diff(np.log(prices))

    # Annualized volatility from daily returns
    daily_vol = np.std(log_returns)
    annual_vol = daily_vol * np.sqrt(365)

    # Identify jumps: returns beyond 3 standard deviations
    threshold = 3.0 * daily_vol
    jumps = log_returns[np.abs(log_returns) > threshold]

    n_days = len(log_returns)
    n_jumps = len(jumps)

    # Jump intensity (annualized)
    jump_intensity = (n_jumps / n_days) * 365 if n_days > 0 else 0.1

    # Mean jump size (negative jumps dominate for slashing)
    jump_size = float(np.mean(jumps)) if n_jumps > 0 else -0.05

    # Remove jump contribution from vol
    non_jump_returns = log_returns[np.abs(log_returns) <= threshold]
    if len(non_jump_returns) > 1:
        diffusion_vol = float(np.std(non_jump_returns) * np.sqrt(365))
    else:
        diffusion_vol = annual_vol

    return PegDynamicsParams(
        peg_vol=max(0.005, diffusion_vol),  # Floor at 0.5%
        peg_jump_intensity=max(0.01, jump_intensity),
        peg_jump_size=min(-0.001, jump_size),  # Ensure negative
        peg_util_correlation=-0.5,  # Keep default; would need utilization data to calibrate
    )
