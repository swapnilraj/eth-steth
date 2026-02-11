"""Aave V3 piecewise linear interest rate model.

Replicates DefaultReserveInterestRateStrategy.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.data.interfaces import ReserveParams


@dataclass(frozen=True)
class InterestRateParams:
    """Parameters for the piecewise linear rate curve."""

    optimal_utilization: float
    base_rate: float
    slope1: float
    slope2: float
    reserve_factor: float


class InterestRateModel:
    """Aave V3 interest rate model (kinked curve)."""

    def __init__(self, params: InterestRateParams | ReserveParams) -> None:
        self.params = params

    def variable_borrow_rate(self, utilization: float) -> float:
        """Compute variable borrow rate for a given utilization.

        Args:
            utilization: Pool utilization ratio in [0, 1].

        Returns:
            Annual borrow rate as a decimal (e.g. 0.05 = 5%).
        """
        p = self.params
        if utilization <= 0:
            return p.base_rate
        if utilization >= 1.0:
            utilization = 1.0

        if utilization <= p.optimal_utilization:
            return p.base_rate + (utilization / p.optimal_utilization) * p.slope1
        else:
            excess = (utilization - p.optimal_utilization) / (
                1.0 - p.optimal_utilization
            )
            return p.base_rate + p.slope1 + excess * p.slope2

    def supply_rate(self, utilization: float) -> float:
        """Compute supply (deposit) rate.

        R_supply = R_borrow * U * (1 - reserve_factor)
        Utilization is clamped to [0, 1] to match variable_borrow_rate.
        """
        utilization = max(0.0, min(1.0, utilization))
        borrow_rate = self.variable_borrow_rate(utilization)
        return borrow_rate * utilization * (1.0 - self.params.reserve_factor)

    def rate_curve(
        self, n_points: int = 200
    ) -> pd.DataFrame:
        """Generate the full rate curve for plotting.

        Returns:
            DataFrame with columns: utilization, borrow_rate, supply_rate
        """
        utilizations = np.linspace(0, 1, n_points)
        borrow_rates = [self.variable_borrow_rate(u) for u in utilizations]
        supply_rates = [self.supply_rate(u) for u in utilizations]

        return pd.DataFrame(
            {
                "utilization": utilizations,
                "borrow_rate": borrow_rates,
                "supply_rate": supply_rates,
            }
        )
