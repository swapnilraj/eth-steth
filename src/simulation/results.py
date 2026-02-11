"""Result dataclasses for simulation outputs."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class MonteCarloResult:
    """Results from a Monte Carlo rate/P&L simulation.

    Attributes:
        utilization_paths: (n_paths, n_steps) array of utilization over time.
        rate_paths: (n_paths, n_steps) array of borrow rates over time.
        pnl_paths: (n_paths, n_steps) array of cumulative P&L over time.
        terminal_pnl: (n_paths,) array of final P&L per path.
        liquidated: (n_paths,) boolean array — True if path hit liquidation.
        timesteps: (n_steps,) array of time in days.
    """

    utilization_paths: np.ndarray
    rate_paths: np.ndarray
    pnl_paths: np.ndarray
    terminal_pnl: np.ndarray
    liquidated: np.ndarray
    timesteps: np.ndarray


@dataclass(frozen=True)
class CascadeStep:
    """A single step in a liquidation cascade."""

    step: int
    debt_liquidated: float
    collateral_seized: float
    total_supply: float
    total_debt: float
    utilization: float
    borrow_rate: float
    at_risk_debt: float


@dataclass(frozen=True)
class CascadeResult:
    """Result of a liquidation cascade simulation."""

    steps: list[CascadeStep]
    total_debt_liquidated: float
    total_collateral_seized: float
    final_utilization: float
    final_borrow_rate: float


@dataclass(frozen=True)
class UnwindCostResult:
    """Detailed cost breakdown for unwinding a position."""

    slippage_cost: float
    price_impact: float
    gas_cost: float
    total_cost: float
    effective_slippage_bps: float
