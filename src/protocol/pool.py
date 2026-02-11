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
        if self.total_supply <= 0:
            return 0.0
        return self.total_debt / self.total_supply

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

        In Aave, a new borrow increases total_debt but total_supply (aToken
        supply) stays the same — the borrowed amount comes from available
        liquidity which is already part of total_supply.

        Returns dict with before/after utilization and rates.
        Does NOT mutate state.
        """
        u_before = self.utilization
        r_borrow_before = self.borrow_rate
        r_supply_before = self.supply_rate

        new_debt = self.state.total_debt + amount
        # total_supply is unchanged — borrow reduces available liquidity,
        # not aToken supply
        u_after = new_debt / self.state.total_supply if self.state.total_supply > 0 else 0.0

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

        A withdrawal reduces total_supply (aToken is burned).
        Debt stays the same, so utilization = debt / new_supply.

        Does NOT mutate state.
        """
        u_before = self.utilization
        r_borrow_before = self.borrow_rate

        new_supply = max(0.0, self.state.total_supply - amount)
        u_after = min(1.0, self.state.total_debt / new_supply) if new_supply > 0 else 1.0

        return {
            "utilization_before": u_before,
            "utilization_after": u_after,
            "borrow_rate_before": r_borrow_before,
            "borrow_rate_after": self.rate_model.variable_borrow_rate(u_after),
        }

    def simulate_liquidation_impact(
        self, liquidated_debt: float
    ) -> dict[str, float]:
        """Simulate how a liquidation event affects the debt pool.

        When ETH debt is liquidated in a cross-asset position (e.g.
        wstETH collateral / WETH debt):
        - WETH pool: debt decreases by liquidated amount, total supply
          stays the same (repaid WETH returns to available liquidity),
          so utilization drops.
        - wstETH pool: collateral is seized (aToken supply drops), but
          that is a separate pool and not modelled here.

        Does NOT mutate state.
        """
        u_before = self.utilization

        new_debt = max(0.0, self.state.total_debt - liquidated_debt)
        # total_supply unchanged — repaid debt returns to available liquidity
        u_after = new_debt / self.state.total_supply if self.state.total_supply > 0 else 0.0

        return {
            "utilization_before": u_before,
            "utilization_after": u_after,
            "borrow_rate_after": self.rate_model.variable_borrow_rate(u_after),
            "supply_rate_after": self.rate_model.supply_rate(u_after),
        }
