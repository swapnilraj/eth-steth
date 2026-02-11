"""Value-at-Risk and tail risk metrics."""

from dataclasses import dataclass

import numpy as np

from src.simulation.results import MonteCarloResult


@dataclass(frozen=True)
class VaRResult:
    """Value-at-Risk and related tail risk metrics.

    All values are in ETH (losses are negative).
    """

    var_95: float  # 5th percentile P&L
    var_99: float  # 1st percentile P&L
    cvar_95: float  # Mean of P&L below VaR95
    cvar_99: float  # Mean of P&L below VaR99
    liquidation_prob: float  # Fraction of paths that hit liquidation
    max_loss: float  # Worst-case P&L


def compute_var(mc_result: MonteCarloResult) -> VaRResult:
    """Compute VaR and CVaR from Monte Carlo simulation results.

    Args:
        mc_result: Output from run_monte_carlo().

    Returns:
        VaRResult with risk metrics.
    """
    pnl = mc_result.terminal_pnl

    var_95 = float(np.percentile(pnl, 5))
    var_99 = float(np.percentile(pnl, 1))

    # CVaR (Expected Shortfall): mean of losses worse than VaR
    tail_95 = pnl[pnl <= var_95]
    cvar_95 = float(np.mean(tail_95)) if len(tail_95) > 0 else var_95

    tail_99 = pnl[pnl <= var_99]
    cvar_99 = float(np.mean(tail_99)) if len(tail_99) > 0 else var_99

    liquidation_prob = float(np.mean(mc_result.liquidated))
    max_loss = float(np.min(pnl))

    return VaRResult(
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        liquidation_prob=liquidation_prob,
        max_loss=max_loss,
    )


def compute_var_from_scenarios(pnl_array: np.ndarray) -> VaRResult:
    """Compute VaR from an array of scenario P&L values.

    Args:
        pnl_array: 1D array of P&L outcomes from correlated scenarios.

    Returns:
        VaRResult with risk metrics (liquidation_prob set to fraction of negative equity).
    """
    var_95 = float(np.percentile(pnl_array, 5))
    var_99 = float(np.percentile(pnl_array, 1))

    tail_95 = pnl_array[pnl_array <= var_95]
    cvar_95 = float(np.mean(tail_95)) if len(tail_95) > 0 else var_95

    tail_99 = pnl_array[pnl_array <= var_99]
    cvar_99 = float(np.mean(tail_99)) if len(tail_99) > 0 else var_99

    max_loss = float(np.min(pnl_array))

    # Approximate liquidation probability as fraction of extreme losses
    # (P&L worse than -50% of mean)
    mean_abs = np.mean(np.abs(pnl_array)) if len(pnl_array) > 0 else 1.0
    liquidation_proxy = float(np.mean(pnl_array < -mean_abs)) if mean_abs > 0 else 0.0

    return VaRResult(
        var_95=var_95,
        var_99=var_99,
        cvar_95=cvar_95,
        cvar_99=cvar_99,
        liquidation_prob=liquidation_proxy,
        max_loss=max_loss,
    )
