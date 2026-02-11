"""Aave V3 liquidation mechanics — health factor, close factor, depeg analysis."""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.protocol.emode import EModeCategory


@dataclass(frozen=True)
class LiquidationParams:
    """Liquidation parameters (may come from standard or E-mode)."""

    ltv: float
    liquidation_threshold: float
    liquidation_bonus: float


class LiquidationModel:
    """Aave V3 liquidation calculations."""

    def __init__(
        self,
        params: LiquidationParams,
        emode: EModeCategory | None = None,
    ) -> None:
        if emode is not None:
            self.ltv = emode.ltv
            self.liquidation_threshold = emode.liquidation_threshold
            self.liquidation_bonus = emode.liquidation_bonus
        else:
            self.ltv = params.ltv
            self.liquidation_threshold = params.liquidation_threshold
            self.liquidation_bonus = params.liquidation_bonus

    def health_factor(
        self, collateral_value: float, debt_value: float
    ) -> float:
        """Compute health factor.

        HF = (collateral_value * liquidation_threshold) / debt_value
        """
        if debt_value <= 0:
            return float("inf")
        return (collateral_value * self.liquidation_threshold) / debt_value

    def close_factor(self, hf: float) -> float:
        """Determine the close factor based on health factor.

        Returns the fraction of debt that can be liquidated.
        - HF >= 0.95: 50% (partial liquidation)
        - HF < 0.95: 100% (full liquidation)
        """
        if hf >= 1.0:
            return 0.0
        if hf >= 0.95:
            return 0.5
        return 1.0

    def max_borrowable(self, collateral_value: float) -> float:
        """Maximum debt value allowed given collateral (using LTV)."""
        return collateral_value * self.ltv

    def liquidation_price_drop(
        self, collateral_value: float, debt_value: float
    ) -> float:
        """Compute the fractional collateral price drop that triggers liquidation.

        Returns the fraction by which collateral value must drop for HF = 1.0.
        A return value of 0.05 means a 5% drop triggers liquidation.
        Returns inf if position has no debt.
        """
        if debt_value <= 0:
            return float("inf")
        # HF = (collateral * (1 - drop) * liq_threshold) / debt = 1.0
        # => drop = 1 - debt / (collateral * liq_threshold)
        critical_ratio = debt_value / (
            collateral_value * self.liquidation_threshold
        )
        if critical_ratio >= 1.0:
            return 0.0  # Already liquidatable
        return 1.0 - critical_ratio

    def depeg_to_liquidation(
        self,
        collateral_amount: float,
        collateral_price: float,
        debt_value: float,
    ) -> float:
        """Compute the stETH/ETH depeg level that triggers liquidation.

        Since Aave uses a 1:1 oracle for wstETH/ETH, the primary risk is a
        depeg in the secondary market. This computes how far stETH must depeg
        from its current price for HF to reach 1.0.

        Returns:
            The peg ratio at which liquidation occurs (e.g. 0.93 means a 7% depeg).
            Returns 0.0 if already liquidatable.
        """
        if debt_value <= 0:
            return 0.0
        # HF = (amount * price * peg_ratio * liq_threshold) / debt = 1.0
        # => peg_ratio = debt / (amount * price * liq_threshold)
        peg_at_liquidation = debt_value / (
            collateral_amount * collateral_price * self.liquidation_threshold
        )
        if peg_at_liquidation >= 1.0:
            return 0.0  # Already liquidatable at current peg
        return peg_at_liquidation

    def depeg_sensitivity(
        self,
        collateral_amount: float,
        collateral_price: float,
        debt_value: float,
        peg_range: tuple[float, float] = (0.85, 1.0),
        n_points: int = 100,
    ) -> pd.DataFrame:
        """Generate health factor sensitivity to stETH/ETH peg changes.

        Returns:
            DataFrame with columns: peg_ratio, health_factor
        """
        pegs = np.linspace(peg_range[0], peg_range[1], n_points)
        hfs = []
        for peg in pegs:
            collateral_value = collateral_amount * collateral_price * peg
            hfs.append(self.health_factor(collateral_value, debt_value))

        return pd.DataFrame({"peg_ratio": pegs, "health_factor": hfs})
