"""Cost-to-unwind estimation with AMM price impact model.

Unwind path for a wstETH collateral / WETH debt position:
  1. Withdraw wstETH from Aave
  2. Unwrap wstETH → stETH (Lido share rate, no slippage)
  3. Swap stETH → ETH on Curve (price impact here)
  4. Wrap ETH → WETH (1:1, no cost)
  5. Repay WETH debt on Aave
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.simulation.results import UnwindCostResult

if TYPE_CHECKING:
    from src.data.dex_liquidity import CurveLiquidity, PoolReserves


@dataclass(frozen=True)
class DEXPoolParams:
    """Parameters for a constant-product AMM pool (x * y = k).

    Used as a fallback when real on-chain swap quotes are not available.
    Note: Curve uses the StableSwap invariant, not constant-product.
    This model is a conservative upper bound for stableswap pools.

    Attributes:
        reserve_x: Reserve of token X (e.g. stETH) in the pool.
        reserve_y: Reserve of token Y (e.g. ETH) in the pool.
        fee_bps: Swap fee in basis points (e.g. 4 = 0.04% for Curve).
    """

    reserve_x: float = 50_000.0
    reserve_y: float = 50_000.0
    fee_bps: float = 4.0


def compute_amm_price_impact(
    trade_size: float,
    pool: DEXPoolParams,
) -> float:
    """Compute price impact for selling `trade_size` of token X into a constant-product pool.

    Uses x * y = k formula: after selling dx of X, you receive
    dy = reserve_y - k / (reserve_x + dx_after_fee).

    Note: This overestimates impact for StableSwap pools like Curve.

    Args:
        trade_size: Amount of token X to sell (e.g. stETH).
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
    gas_price_gwei: float = 30.0,
    gas_units: int = 500_000,
) -> float:
    """Estimate gas cost in ETH for an unwind transaction.

    A full unwind (flash loan + repay + withdraw + unwrap + swap + wrap +
    repay flash loan) typically costs 400-600k gas.

    Args:
        gas_price_gwei: Gas price in gwei.
        gas_units: Estimated gas units for the full unwind.

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
        debt_amount: Total debt to repay (WETH).
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
    dex_reserves: PoolReserves | None = None,
    curve_liquidity: CurveLiquidity | None = None,
    wsteth_rate: float = 1.18,
) -> UnwindCostResult:
    """Detailed unwind cost estimation.

    Priority order:
    1. ``curve_liquidity`` — real Curve ``get_dy()`` on-chain (StableSwap invariant)
    2. ``dex_reserves`` — build constant-product pool from reserves (conservative)
    3. ``pool`` — manual constant-product pool params
    4. Linear slippage fallback

    The unwind path is: wstETH → unwrap → stETH → Curve → ETH → WETH.
    The ``wsteth_rate`` converts between wstETH and stETH (1 wstETH ≈ 1.18 stETH).

    Args:
        debt_amount: Total WETH debt to repay.
        pool: Fallback constant-product pool parameters.
        gas_price_gwei: Gas price for cost estimation.
        slippage_bps: Fallback linear slippage if no pool model available.
        dex_reserves: Optional real DEX pool reserves (stETH/ETH from Curve).
        curve_liquidity: Optional Curve pool interface for real swap quotes.
        wsteth_rate: wstETH/stETH conversion rate (1 wstETH = rate stETH).

    Returns:
        UnwindCostResult with detailed breakdown.
    """
    gas_cost = estimate_gas_cost(gas_price_gwei=gas_price_gwei)

    # To repay debt_amount WETH, we need debt_amount ETH from the swap.
    # We sell stETH on Curve to get ETH.
    # At ~1:1 stETH/ETH peg, need ~debt_amount stETH.
    steth_to_sell = debt_amount  # Approximate: need debt_amount ETH output

    if curve_liquidity is not None:
        # Best option: real StableSwap quote via get_dy()
        try:
            quote = curve_liquidity.get_swap_output(steth_to_sell)
            eth_received = quote.output_amount
            # Shortfall: how much less ETH we get vs selling at 1:1
            shortfall = steth_to_sell - eth_received
            slippage_cost = max(0.0, shortfall)
            price_impact = slippage_cost / debt_amount if debt_amount > 0 else 0.0
            effective_bps = price_impact * 10_000

            return UnwindCostResult(
                slippage_cost=slippage_cost,
                price_impact=price_impact,
                gas_cost=gas_cost,
                total_cost=slippage_cost + gas_cost,
                effective_slippage_bps=effective_bps,
            )
        except Exception:
            pass  # Fall through to constant-product fallback

    # Build effective pool for constant-product model
    effective_pool = pool
    if dex_reserves is not None:
        effective_pool = DEXPoolParams(
            reserve_x=dex_reserves.reserve_token0,
            reserve_y=dex_reserves.reserve_token1,
            fee_bps=dex_reserves.fee_bps,
        )

    if effective_pool is not None:
        # Constant-product approximation (overestimates for StableSwap)
        # Trade size = stETH to sell ≈ debt_amount
        price_impact = compute_amm_price_impact(steth_to_sell, effective_pool)
        slippage_cost = debt_amount * price_impact
        effective_bps = price_impact * 10_000
    else:
        # Linear fallback
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
