"""DEX liquidity queries for Curve and Uniswap V3 pools."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PoolReserves:
    """Reserves snapshot for a DEX pool."""

    reserve_token0: float  # stETH or wstETH
    reserve_token1: float  # ETH or WETH
    fee_bps: float         # Swap fee in basis points


@dataclass(frozen=True)
class SwapQuote:
    """Result of a swap quote query."""

    input_amount: float
    output_amount: float
    price_impact: float    # Fractional (0.01 = 1%)
    source: str            # "curve", "uniswap"


class CurveLiquidity:
    """Query Curve stETH/ETH pool for reserves and swap quotes.

    Pool: 0xDC24316b9AE028F1497c275EB9192a3Ea0f67022
    Coin 0 = stETH, Coin 1 = ETH
    Fee: ~4 bps (0.04%)
    """

    def __init__(self, w3: Any) -> None:
        from src.data.contracts import CURVE_POOL_ABI, CURVE_STETH_ETH_POOL

        self._w3 = w3
        self._pool = w3.eth.contract(
            address=w3.to_checksum_address(CURVE_STETH_ETH_POOL),
            abi=CURVE_POOL_ABI,
        )

    def get_reserves(self) -> PoolReserves:
        """Fetch current pool reserves."""
        steth_balance = self._pool.functions.balances(0).call() / 1e18
        eth_balance = self._pool.functions.balances(1).call() / 1e18
        return PoolReserves(
            reserve_token0=steth_balance,
            reserve_token1=eth_balance,
            fee_bps=4.0,  # Curve stETH pool fee
        )

    def get_swap_output(self, sell_steth_amount: float) -> SwapQuote:
        """Get expected ETH output for selling stETH via Curve.

        Args:
            sell_steth_amount: Amount of stETH to sell.

        Returns:
            SwapQuote with output amount and price impact.
        """
        amount_wei = int(sell_steth_amount * 1e18)
        # Coin 0 = stETH, Coin 1 = ETH; selling stETH (0) for ETH (1)
        output_wei = self._pool.functions.get_dy(0, 1, amount_wei).call()
        output = output_wei / 1e18

        # Price impact vs 1:1 peg (stETH should trade ~1:1 with ETH)
        price_impact = 1.0 - (output / sell_steth_amount) if sell_steth_amount > 0 else 0.0

        return SwapQuote(
            input_amount=sell_steth_amount,
            output_amount=output,
            price_impact=max(0.0, price_impact),
            source="curve",
        )


