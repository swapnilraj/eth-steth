"""Cost-to-unwind estimation with AMM price impact model."""

from dataclasses import dataclass

from src.simulation.results import UnwindCostResult


@dataclass(frozen=True)
class DEXPoolParams:
    """Parameters for a constant-product AMM pool (x * y = k).

    Attributes:
        reserve_x: Reserve of token X (e.g. wstETH) in the pool.
        reserve_y: Reserve of token Y (e.g. WETH) in the pool.
        fee_bps: Swap fee in basis points (e.g. 30 = 0.30%).
    """

    reserve_x: float = 50_000.0
    reserve_y: float = 59_000.0  # 50k wstETH * 1.18
    fee_bps: float = 30.0


def compute_amm_price_impact(
    trade_size: float,
    pool: DEXPoolParams,
) -> float:
    """Compute price impact for selling `trade_size` of token X into a constant-product pool.

    Uses x * y = k formula: after selling dx of X, you receive
    dy = reserve_y - k / (reserve_x + dx_after_fee).

    Args:
        trade_size: Amount of token X to sell.
        pool: DEX pool parameters.

    Returns:
        Price impact as a fraction (e.g. 0.01 = 1% worse than spot).
    """
    if trade_size <= 0:
        return 0.0

    fee_fraction = pool.fee_bps / 10_000
    dx_after_fee = trade_size * (1.0 - fee_fraction)

    k = pool.reserve_x * pool.reserve_y
    new_reserve_x = pool.reserve_x + dx_after_fee
    new_reserve_y = k / new_reserve_x

    dy = pool.reserve_y - new_reserve_y

    # Spot price = reserve_y / reserve_x
    spot_price = pool.reserve_y / pool.reserve_x
    expected_dy = trade_size * spot_price

    if expected_dy <= 0:
        return 0.0

    price_impact = 1.0 - (dy / expected_dy)
    return max(0.0, price_impact)


def estimate_gas_cost(
    eth_price_usd: float = 2000.0,
    gas_price_gwei: float = 30.0,
    gas_units: int = 300_000,
) -> float:
    """Estimate gas cost in ETH for an unwind transaction.

    Args:
        eth_price_usd: ETH price in USD (not used in ETH terms, but for context).
        gas_price_gwei: Gas price in gwei.
        gas_units: Estimated gas units for the swap + repay transaction.

    Returns:
        Gas cost in ETH.
    """
    return gas_units * gas_price_gwei * 1e-9


def estimate_unwind_cost(
    debt_amount: float,
    slippage_bps: float = 10.0,
) -> float:
    """Estimate the cost to fully unwind the position.

    Backward-compatible simple slippage estimate.

    Args:
        debt_amount: Total debt to repay.
        slippage_bps: Expected slippage in basis points.

    Returns:
        Estimated cost in ETH.
    """
    return debt_amount * (slippage_bps / 10_000)


def estimate_unwind_cost_detailed(
    debt_amount: float,
    pool: DEXPoolParams | None = None,
    gas_price_gwei: float = 30.0,
    slippage_bps: float = 10.0,
) -> UnwindCostResult:
    """Detailed unwind cost estimation with AMM price impact.

    When a pool is provided, uses the constant-product AMM model.
    Otherwise falls back to linear slippage.

    Args:
        debt_amount: Total debt to repay (need to sell this much wstETH equivalent).
        pool: DEX pool parameters. If None, uses simple linear model.
        gas_price_gwei: Gas price for cost estimation.
        slippage_bps: Fallback slippage if no pool provided.

    Returns:
        UnwindCostResult with detailed breakdown.
    """
    gas_cost = estimate_gas_cost(gas_price_gwei=gas_price_gwei)

    if pool is not None:
        # Use AMM model: need to sell enough wstETH to cover debt
        # Approximate trade size as debt_amount (in wstETH-equivalent terms)
        spot_price = pool.reserve_y / pool.reserve_x
        trade_size_x = debt_amount / spot_price if spot_price > 0 else debt_amount

        price_impact = compute_amm_price_impact(trade_size_x, pool)
        slippage_cost = debt_amount * price_impact
        effective_bps = price_impact * 10_000
    else:
        price_impact = slippage_bps / 10_000
        slippage_cost = debt_amount * price_impact
        effective_bps = slippage_bps

    total_cost = slippage_cost + gas_cost

    return UnwindCostResult(
        slippage_cost=slippage_cost,
        price_impact=price_impact,
        gas_cost=gas_cost,
        total_cost=total_cost,
        effective_slippage_bps=effective_bps,
    )
