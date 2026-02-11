"""Iterative liquidation cascade simulation."""

from dataclasses import dataclass

from src.protocol.interest_rate import InterestRateModel, InterestRateParams
from src.protocol.pool import PoolState
from src.simulation.results import CascadeResult, CascadeStep


@dataclass(frozen=True)
class CascadeConfig:
    """Configuration for a liquidation cascade simulation.

    Attributes:
        initial_debt_to_liquidate: Starting debt amount to liquidate (WETH).
        collateral_price: wstETH/ETH price for debt→collateral conversion.
        liquidation_bonus: Fraction bonus for liquidators (e.g. 0.01 = 1%).
        rate_sensitivity: Fraction of debt that becomes at-risk per 1% rate increase.
        max_steps: Maximum cascade iterations.
        min_debt_threshold: Stop cascade when at-risk debt falls below this.
    """

    initial_debt_to_liquidate: float
    collateral_price: float = 1.18
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

    Models the WETH debt pool correctly: when debt is liquidated, the
    liquidator repays WETH debt, so total_debt decreases but total_supply
    (aToken supply) stays the same. Utilization = debt / supply drops,
    and borrow rates fall.

    Collateral seizure happens in the wstETH pool (separate) and is
    converted using collateral_price for reporting, but does not affect
    WETH pool utilization.

    Cascade propagation comes from borrowers whose positions become
    unhealthy due to rate changes or peg movements, not from the WETH
    pool mechanics alone. The rate_sensitivity parameter models this
    second-order effect as a heuristic.

    Does NOT mutate the input pool_state.

    Args:
        pool_state: Current WETH pool state snapshot.
        rate_params: Interest rate curve parameters.
        config: Cascade configuration.

    Returns:
        CascadeResult with per-step details and totals.
    """
    rate_model = InterestRateModel(rate_params)

    # Work with copies of the WETH pool
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

        # Collateral seized in wstETH terms:
        # seized = (debt_repaid * (1 + bonus)) / collateral_price
        collateral_seized = (
            debt_to_liquidate * (1.0 + config.liquidation_bonus) / config.collateral_price
        )

        # Update WETH pool: debt decreases, supply stays the same
        # (repaid WETH returns to available liquidity within the pool)
        debt -= debt_to_liquidate

        total_debt_liquidated += debt_to_liquidate
        total_collateral_seized += collateral_seized

        # Recompute utilization: debt / supply (supply unchanged)
        utilization = debt / supply if supply > 0 else 0.0
        new_rate = rate_model.variable_borrow_rate(utilization)

        # Estimate new at-risk debt from rate change.
        # After liquidation, WETH utilization drops → rates drop.
        # But in a depeg scenario many positions become unhealthy
        # simultaneously, so the cascade may still propagate.
        # rate_sensitivity is a heuristic for this second-order effect.
        rate_change_pct = (new_rate - prev_rate) * 100.0  # percentage points
        # Only positive rate changes create new at-risk debt
        at_risk_debt = max(0.0, debt * config.rate_sensitivity * rate_change_pct)

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
    final_util = debt / supply if supply > 0 else 0.0
    final_rate = rate_model.variable_borrow_rate(final_util)

    return CascadeResult(
        steps=steps,
        total_debt_liquidated=total_debt_liquidated,
        total_collateral_seized=total_collateral_seized,
        final_utilization=final_util,
        final_borrow_rate=final_rate,
    )
