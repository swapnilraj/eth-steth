"""Iterative liquidation cascade simulation."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.data.aave_positions import AavePosition
from src.data.dex_liquidity import CurveLiquidity
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
            Used as fallback when ``curve_liquidity`` is not provided.
        depeg_sensitivity: Multiplier converting a fractional peg drop into
            the fraction of remaining debt that becomes at-risk.  E.g. 5.0
            means a 10% peg drop puts 50% of debt at risk (5.0 x 0.10).
            Used as fallback when ``positions`` are not provided.
        max_steps: Maximum cascade iterations.
        min_debt_threshold: Stop cascade when at-risk debt falls below this.
        positions: Optional list of real Aave positions from the subgraph.
            When provided, the cascade uses actual position HFs to determine
            at-risk debt instead of the heuristic ``depeg_sensitivity``
            multiplier.
        curve_liquidity: Optional Curve pool interface for computing price
            impact from selling seized wstETH. When provided, replaces the
            linear ``price_impact_per_unit`` model with real Curve pool
            swap output.
    """

    initial_debt_to_liquidate: float
    collateral_price: float = 1.18
    liquidation_bonus: float = 0.01
    price_impact_per_unit: float = 0.00001
    depeg_sensitivity: float = 5.0
    max_steps: int = 10
    min_debt_threshold: float = 100.0
    positions: list[AavePosition] | None = None
    curve_liquidity: CurveLiquidity | None = None


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

        # Price impact: selling seized wstETH depresses the peg.
        # Clamp to 99% max drop per step to prevent negative prices.
        peg_drop = min(collateral_seized * config.price_impact_per_unit, 0.99)
        collateral_price = collateral_price * (1.0 - peg_drop)
        if collateral_price < 0.01:
            collateral_price = 0.01  # floor for numerical stability

        # Recompute WETH utilization and rate
        utilization = debt / supply if supply > 0 else 0.0
        new_rate = rate_model.variable_borrow_rate(utilization)

        # At-risk debt: fraction of remaining debt that becomes unhealthy
        # due to the further depeg.
        # at_risk = debt × depeg_sensitivity × peg_drop  (all fractional)
        at_risk_debt = max(0.0, debt * config.depeg_sensitivity * peg_drop)

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


def _compute_price_impact(
    collateral_seized: float,
    config: CascadeConfig,
) -> float:
    """Compute fractional peg drop from selling seized wstETH.

    When ``config.curve_liquidity`` is available, the price impact comes
    from the real Curve pool swap output.  Otherwise falls back to the
    linear ``price_impact_per_unit`` model.

    Returns:
        Fractional peg drop, clamped to [0, 0.99].
    """
    if collateral_seized <= 0:
        return 0.0

    if config.curve_liquidity is not None:
        quote = config.curve_liquidity.get_swap_output(collateral_seized)
        # price_impact from CurveLiquidity is already a fraction (e.g. 0.01 = 1%)
        peg_drop = max(0.0, quote.price_impact)
    else:
        peg_drop = collateral_seized * config.price_impact_per_unit

    return min(peg_drop, 0.99)


def _find_at_risk_positions(
    positions: list[AavePosition],
    collateral_price: float,
    liquidation_threshold: float,
    already_liquidated: set[str],
) -> list[AavePosition]:
    """Find positions with HF < 1.0 at the given collateral price.

    Recomputes each position's health factor using the current
    ``collateral_price`` and returns those that are underwater,
    excluding positions already liquidated in prior steps.

    Args:
        positions: All positions, sorted by HF ascending.
        collateral_price: Current wstETH/ETH price after depeg.
        liquidation_threshold: E-mode or standard liquidation threshold.
        already_liquidated: Set of user addresses already liquidated.

    Returns:
        List of positions with recomputed HF < 1.0.
    """
    at_risk: list[AavePosition] = []
    for pos in positions:
        if pos.user in already_liquidated:
            continue
        if pos.debt_weth <= 0:
            continue
        collateral_value = pos.collateral_wsteth * collateral_price
        hf = (collateral_value * liquidation_threshold) / pos.debt_weth
        if hf < 1.0:
            at_risk.append(pos)
    return at_risk


def simulate_cascade_with_positions(
    positions: list[AavePosition],
    initial_peg_shock: float,
    pool_state: PoolState,
    rate_params: InterestRateParams,
    collateral_price: float = 1.18,
    liquidation_threshold: float = 0.955,
    liquidation_bonus: float = 0.01,
    max_steps: int = 10,
    min_debt_threshold: float = 100.0,
    price_impact_per_unit: float = 0.00001,
    curve_liquidity: CurveLiquidity | None = None,
) -> CascadeResult:
    """Simulate a liquidation cascade using real Aave positions.

    Instead of using a heuristic ``depeg_sensitivity`` multiplier, this
    function iterates over actual on-chain positions sorted by health
    factor.  At each step it:

      1. Applies the current peg to find positions with HF < 1.0.
      2. Liquidates those positions (seizes collateral, reduces debt).
      3. Computes price impact from selling the seized wstETH
         (via Curve if available, otherwise linear model).
      4. Updates the peg and rechecks remaining positions.

    Does NOT mutate the input ``pool_state`` or ``positions``.

    Args:
        positions: Real Aave positions from the subgraph (will be sorted
            by health factor ascending internally).
        initial_peg_shock: Fractional peg drop to apply before the first
            iteration (e.g. 0.05 = 5% depeg).  The collateral price is
            multiplied by ``(1 - initial_peg_shock)``.
        pool_state: Current WETH pool state snapshot.
        rate_params: Interest rate curve parameters.
        collateral_price: Initial wstETH/ETH price before shock.
        liquidation_threshold: Aave liquidation threshold (0.955 for E-mode).
        liquidation_bonus: Fraction bonus for liquidators (e.g. 0.01 = 1%).
        max_steps: Maximum cascade iterations.
        min_debt_threshold: Stop when total at-risk debt in a round falls
            below this amount.
        price_impact_per_unit: Fallback linear price impact model.  Only
            used when ``curve_liquidity`` is not provided.
        curve_liquidity: Optional Curve pool interface for real price
            impact computation.

    Returns:
        CascadeResult with per-step details and totals.
    """
    rate_model = InterestRateModel(rate_params)

    # Sort positions by HF ascending (most at-risk first)
    sorted_positions = sorted(positions, key=lambda p: p.health_factor)

    # Build a CascadeConfig for _compute_price_impact helper
    impact_config = CascadeConfig(
        initial_debt_to_liquidate=0.0,  # unused by helper
        collateral_price=collateral_price,
        liquidation_bonus=liquidation_bonus,
        price_impact_per_unit=price_impact_per_unit,
        curve_liquidity=curve_liquidity,
    )

    supply = pool_state.total_supply
    debt = pool_state.total_debt

    # Apply initial peg shock
    current_price = collateral_price * (1.0 - initial_peg_shock)
    if current_price < 0.01:
        current_price = 0.01

    steps: list[CascadeStep] = []
    total_debt_liquidated = 0.0
    total_collateral_seized = 0.0
    already_liquidated: set[str] = set()

    for step_num in range(max_steps):
        # Find positions that are now underwater
        at_risk = _find_at_risk_positions(
            sorted_positions,
            current_price,
            liquidation_threshold,
            already_liquidated,
        )

        if not at_risk:
            break

        # Aggregate debt and collateral to liquidate in this round
        step_debt = 0.0
        step_collateral = 0.0

        for pos in at_risk:
            # Recompute HF to determine close factor
            collateral_value = pos.collateral_wsteth * current_price
            hf = (collateral_value * liquidation_threshold) / pos.debt_weth
            if hf >= 0.95:
                close_factor = 0.5
            else:
                close_factor = 1.0

            debt_to_liq = pos.debt_weth * close_factor
            seized = debt_to_liq * (1.0 + liquidation_bonus) / current_price

            step_debt += debt_to_liq
            step_collateral += seized

            # Mark fully-liquidated positions; partially-liquidated ones
            # remain eligible for future rounds at reduced size, but since
            # AavePosition is frozen we mark all as done for simplicity.
            already_liquidated.add(pos.user)

        if step_debt < min_debt_threshold:
            break

        # Cap at available pool debt
        if step_debt > debt:
            step_debt = debt
            step_collateral = step_debt * (1.0 + liquidation_bonus) / current_price

        # Update pool state
        debt -= step_debt
        total_debt_liquidated += step_debt
        total_collateral_seized += step_collateral

        # Compute price impact from selling seized collateral
        peg_drop = _compute_price_impact(step_collateral, impact_config)
        current_price = current_price * (1.0 - peg_drop)
        if current_price < 0.01:
            current_price = 0.01

        # Recompute WETH utilization and rate
        utilization = debt / supply if supply > 0 else 0.0
        new_rate = rate_model.variable_borrow_rate(utilization)

        # Compute at-risk debt for reporting (how much debt is still
        # underwater after this round's price impact)
        remaining_at_risk = _find_at_risk_positions(
            sorted_positions,
            current_price,
            liquidation_threshold,
            already_liquidated,
        )
        at_risk_debt = sum(p.debt_weth for p in remaining_at_risk)

        steps.append(
            CascadeStep(
                step=step_num + 1,
                debt_liquidated=step_debt,
                collateral_seized=step_collateral,
                total_supply=supply,
                total_debt=debt,
                utilization=utilization,
                borrow_rate=new_rate,
                collateral_price=current_price,
                at_risk_debt=at_risk_debt,
            )
        )

    final_util = debt / supply if supply > 0 else 0.0
    final_rate = rate_model.variable_borrow_rate(final_util)

    return CascadeResult(
        steps=steps,
        total_debt_liquidated=total_debt_liquidated,
        total_collateral_seized=total_collateral_seized,
        final_utilization=final_util,
        final_borrow_rate=final_rate,
    )
