"""Aave V3 pool state and simulation model."""

from dataclasses import dataclass

from src.data.interfaces import ReserveState
from src.protocol.interest_rate import InterestRateModel


@dataclass
class PoolState:
    """Mutable pool state for simulation."""

    total_supply: float
    total_debt: float

    @property
    def utilization(self) -> float:
        total = self.total_supply + self.total_debt
        if total <= 0:
            return 0.0
        return self.total_debt / total

    @classmethod
    def from_reserve_state(cls, state: ReserveState) -> "PoolState":
        return cls(total_supply=state.total_supply, total_debt=state.total_debt)


class PoolModel:
    """Pool simulation combining state with rate model."""

    def __init__(self, state: PoolState, rate_model: InterestRateModel) -> None:
        self.state = state
        self.rate_model = rate_model

    @property
    def utilization(self) -> float:
        return self.state.utilization

    @property
    def borrow_rate(self) -> float:
        return self.rate_model.variable_borrow_rate(self.utilization)

    @property
    def supply_rate(self) -> float:
        return self.rate_model.supply_rate(self.utilization)

    def simulate_borrow(self, amount: float) -> dict[str, float]:
        """Simulate the impact of an additional borrow on rates.

        Returns dict with before/after utilization and rates.
        Does NOT mutate state.
        """
        u_before = self.utilization
        r_borrow_before = self.borrow_rate
        r_supply_before = self.supply_rate

        new_debt = self.state.total_debt + amount
        new_supply = self.state.total_supply - amount  # Borrow reduces available
        new_total = new_supply + new_debt
        u_after = new_debt / new_total if new_total > 0 else 0.0

        return {
            "utilization_before": u_before,
            "utilization_after": u_after,
            "borrow_rate_before": r_borrow_before,
            "borrow_rate_after": self.rate_model.variable_borrow_rate(u_after),
            "supply_rate_before": r_supply_before,
            "supply_rate_after": self.rate_model.supply_rate(u_after),
        }

    def simulate_withdrawal(self, amount: float) -> dict[str, float]:
        """Simulate the impact of a supply withdrawal on rates.

        Does NOT mutate state.
        """
        u_before = self.utilization
        r_borrow_before = self.borrow_rate

        new_supply = self.state.total_supply - amount
        new_total = new_supply + self.state.total_debt
        u_after = self.state.total_debt / new_total if new_total > 0 else 0.0

        return {
            "utilization_before": u_before,
            "utilization_after": u_after,
            "borrow_rate_before": r_borrow_before,
            "borrow_rate_after": self.rate_model.variable_borrow_rate(u_after),
        }

    def simulate_liquidation_impact(
        self, liquidated_debt: float, seized_collateral_supply: float
    ) -> dict[str, float]:
        """Simulate how a liquidation event affects pool state.

        When ETH debt is liquidated:
        - debt decreases by liquidated amount
        - supply decreases by seized collateral (transferred to liquidator)

        Does NOT mutate state.
        """
        u_before = self.utilization

        new_debt = self.state.total_debt - liquidated_debt
        new_supply = self.state.total_supply - seized_collateral_supply
        new_total = new_supply + new_debt
        u_after = new_debt / new_total if new_total > 0 else 0.0

        return {
            "utilization_before": u_before,
            "utilization_after": u_after,
            "borrow_rate_after": self.rate_model.variable_borrow_rate(u_after),
            "supply_rate_after": self.rate_model.supply_rate(u_after),
        }
