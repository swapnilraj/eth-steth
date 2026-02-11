"""Iterative liquidation cascade simulation."""

from dataclasses import dataclass

from src.protocol.interest_rate import InterestRateModel, InterestRateParams
from src.protocol.pool import PoolState
from src.simulation.results import CascadeResult, CascadeStep


@dataclass(frozen=True)
class CascadeConfig:
    """Configuration for a liquidation cascade simulation.

    The cascade is driven by price impact: selling seized wstETH on the
    market pushes the peg down, which makes more positions unhealthy.
    This is the real-world cascade mechanism for cross-asset positions
    (wstETH collateral / WETH debt).

    Attributes:
        initial_debt_to_liquidate: Starting debt amount to liquidate (WETH).
        collateral_price: Initial wstETH/ETH price.
        liquidation_bonus: Fraction bonus for liquidators (e.g. 0.01 = 1%).
        price_impact_per_unit: Fractional peg drop per unit of wstETH sold.
            E.g. 0.00001 means selling 10,000 wstETH drops the peg by 10%.
        depeg_sensitivity: Fraction of remaining debt that becomes at-risk
            per 1% further depeg.  E.g. 0.10 means a 1% depeg puts 10% of
            outstanding debt at risk of liquidation.
        max_steps: Maximum cascade iterations.
        min_debt_threshold: Stop cascade when at-risk debt falls below this.
    """

    initial_debt_to_liquidate: float
    collateral_price: float = 1.18
    liquidation_bonus: float = 0.01
    price_impact_per_unit: float = 0.00001
    depeg_sensitivity: float = 0.10
    max_steps: int = 10
    min_debt_threshold: float = 100.0


def simulate_cascade(
    pool_state: PoolState,
    rate_params: InterestRateParams,
    config: CascadeConfig,
) -> CascadeResult:
    """Simulate an iterative liquidation cascade.

    Cascade mechanism (price-impact driven):
      1. Liquidate debt → seize wstETH collateral
      2. Liquidators sell seized wstETH → price impact depresses peg
      3. Lower peg → more positions breach HF → new at-risk debt
      4. Repeat until at-risk debt falls below threshold

    WETH pool mechanics: debt decreases, supply stays the same (repaid
    WETH returns to available liquidity).  Collateral seizure is in the
    wstETH pool (separate from WETH).

    Does NOT mutate the input pool_state.

    Args:
        pool_state: Current WETH pool state snapshot.
        rate_params: Interest rate curve parameters.
        config: Cascade configuration.

    Returns:
        CascadeResult with per-step details and totals.
    """
    rate_model = InterestRateModel(rate_params)

    supply = pool_state.total_supply
    debt = pool_state.total_debt
    collateral_price = config.collateral_price

    steps: list[CascadeStep] = []
    total_debt_liquidated = 0.0
    total_collateral_seized = 0.0

    debt_to_liquidate = config.initial_debt_to_liquidate

    for step_num in range(config.max_steps):
        if debt_to_liquidate < config.min_debt_threshold:
            break
        if debt_to_liquidate > debt:
            debt_to_liquidate = debt

        # Collateral seized in wstETH terms
        collateral_seized = (
            debt_to_liquidate * (1.0 + config.liquidation_bonus) / collateral_price
        )

        # WETH pool: debt decreases, supply unchanged
        debt -= debt_to_liquidate
        total_debt_liquidated += debt_to_liquidate
        total_collateral_seized += collateral_seized

        # Price impact: selling seized wstETH depresses the peg
        peg_drop = collateral_seized * config.price_impact_per_unit
        collateral_price = collateral_price * (1.0 - peg_drop)
        if collateral_price < 0.01:
            collateral_price = 0.01  # floor

        # Recompute WETH utilization and rate
        utilization = debt / supply if supply > 0 else 0.0
        new_rate = rate_model.variable_borrow_rate(utilization)

        # At-risk debt: fraction of remaining debt that becomes unhealthy
        # due to the further depeg.  depeg_sensitivity = fraction per 1% depeg.
        depeg_pct = peg_drop * 100.0
        at_risk_debt = max(0.0, debt * config.depeg_sensitivity * depeg_pct)

        steps.append(
            CascadeStep(
                step=step_num + 1,
                debt_liquidated=debt_to_liquidate,
                collateral_seized=collateral_seized,
                total_supply=supply,
                total_debt=debt,
                utilization=utilization,
                borrow_rate=new_rate,
                collateral_price=collateral_price,
                at_risk_debt=at_risk_debt,
            )
        )

        debt_to_liquidate = at_risk_debt

    final_util = debt / supply if supply > 0 else 0.0
    final_rate = rate_model.variable_borrow_rate(final_util)

    return CascadeResult(
        steps=steps,
        total_debt_liquidated=total_debt_liquidated,
        total_collateral_seized=total_collateral_seized,
        final_utilization=final_util,
        final_borrow_rate=final_rate,
    )
