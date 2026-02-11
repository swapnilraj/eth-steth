"""Iterative liquidation cascade simulation."""

from dataclasses import dataclass

from src.protocol.interest_rate import InterestRateModel, InterestRateParams
from src.protocol.pool import PoolState
from src.simulation.results import CascadeResult, CascadeStep


@dataclass(frozen=True)
class CascadeConfig:
    """Configuration for a liquidation cascade simulation.

    Attributes:
        initial_debt_to_liquidate: Starting debt amount to liquidate.
        liquidation_bonus: Fraction bonus for liquidators (e.g. 0.01 = 1%).
        rate_sensitivity: Fraction of debt that becomes at-risk per 1% rate increase.
        max_steps: Maximum cascade iterations.
        min_debt_threshold: Stop cascade when at-risk debt falls below this.
    """

    initial_debt_to_liquidate: float
    liquidation_bonus: float = 0.01
    rate_sensitivity: float = 0.05
    max_steps: int = 10
    min_debt_threshold: float = 100.0


def simulate_cascade(
    pool_state: PoolState,
    rate_params: InterestRateParams,
    config: CascadeConfig,
) -> CascadeResult:
    """Simulate an iterative liquidation cascade.

    Each step: liquidate debt -> seize collateral -> update pool ->
    recompute rate -> estimate new at-risk debt from rate increase -> repeat.

    Does NOT mutate the input pool_state.

    Args:
        pool_state: Current pool state snapshot.
        rate_params: Interest rate curve parameters.
        config: Cascade configuration.

    Returns:
        CascadeResult with per-step details and totals.
    """
    rate_model = InterestRateModel(rate_params)

    # Work with copies
    supply = pool_state.total_supply
    debt = pool_state.total_debt
    prev_rate = rate_model.variable_borrow_rate(pool_state.utilization)

    steps: list[CascadeStep] = []
    total_debt_liquidated = 0.0
    total_collateral_seized = 0.0

    debt_to_liquidate = config.initial_debt_to_liquidate

    for step_num in range(config.max_steps):
        if debt_to_liquidate < config.min_debt_threshold:
            break
        if debt_to_liquidate > debt:
            debt_to_liquidate = debt

        # Collateral seized = debt * (1 + bonus)
        collateral_seized = debt_to_liquidate * (1.0 + config.liquidation_bonus)

        # Update pool state
        debt -= debt_to_liquidate
        supply -= collateral_seized
        if supply < 0:
            supply = 0.0

        total_debt_liquidated += debt_to_liquidate
        total_collateral_seized += collateral_seized

        # Recompute utilization and rate
        total = supply + debt
        utilization = debt / total if total > 0 else 0.0
        new_rate = rate_model.variable_borrow_rate(utilization)

        # Estimate new at-risk debt from rate increase
        rate_increase_pct = (new_rate - prev_rate) * 100.0  # in percentage points
        at_risk_debt = max(0.0, debt * config.rate_sensitivity * rate_increase_pct)

        steps.append(
            CascadeStep(
                step=step_num + 1,
                debt_liquidated=debt_to_liquidate,
                collateral_seized=collateral_seized,
                total_supply=supply,
                total_debt=debt,
                utilization=utilization,
                borrow_rate=new_rate,
                at_risk_debt=at_risk_debt,
            )
        )

        prev_rate = new_rate
        debt_to_liquidate = at_risk_debt

    # Final state
    total = supply + debt
    final_util = debt / total if total > 0 else 0.0
    final_rate = rate_model.variable_borrow_rate(final_util)

    return CascadeResult(
        steps=steps,
        total_debt_liquidated=total_debt_liquidated,
        total_collateral_seized=total_collateral_seized,
        final_utilization=final_util,
        final_borrow_rate=final_rate,
    )
