"""Static data provider with hardcoded Aave V3 parameters."""

from src.data.constants import EMODE_ETH_CORRELATED, WETH, WSTETH
from src.data.interfaces import (
    LiquidationParams,
    PoolDataProvider,
    ReserveParams,
    ReserveState,
)
from src.protocol.emode import EModeCategory

# --- Hardcoded parameters sourced from Aave V3 governance ---

_RESERVE_PARAMS: dict[str, ReserveParams] = {
    WETH: ReserveParams(
        optimal_utilization=0.92,
        base_rate=0.0,
        slope1=0.027,
        slope2=0.40,
        reserve_factor=0.15,
    ),
    WSTETH: ReserveParams(
        optimal_utilization=0.80,
        base_rate=0.0,
        slope1=0.01,
        slope2=0.40,
        reserve_factor=0.35,
    ),
}

_LIQUIDATION_PARAMS: dict[str, LiquidationParams] = {
    WETH: LiquidationParams(
        ltv=0.805,
        liquidation_threshold=0.83,
        liquidation_bonus=0.05,
    ),
    WSTETH: LiquidationParams(
        ltv=0.795,
        liquidation_threshold=0.81,
        liquidation_bonus=0.07,
    ),
}

_EMODE_CATEGORIES: dict[int, EModeCategory] = {
    EMODE_ETH_CORRELATED: EModeCategory(
        category_id=EMODE_ETH_CORRELATED,
        label="ETH correlated",
        ltv=0.935,
        liquidation_threshold=0.955,
        liquidation_bonus=0.01,
    ),
}

# Default pool states (representative snapshot)
_RESERVE_STATES: dict[str, ReserveState] = {
    WETH: ReserveState(
        total_supply=2_800_000.0,
        total_debt=2_200_000.0,
    ),
    WSTETH: ReserveState(
        total_supply=2_400_000.0,
        total_debt=50_000.0,
    ),
}

# Prices in ETH terms
_ASSET_PRICES: dict[str, float] = {
    WETH: 1.0,
    WSTETH: 1.18,  # wstETH/ETH exchange rate (includes staking rewards)
}

_STETH_ETH_PEG = 1.0  # Perfect peg by default


class StaticDataProvider(PoolDataProvider):
    """Data provider using hardcoded Aave V3 mainnet parameters."""

    def get_reserve_params(self, asset: str) -> ReserveParams:
        return _RESERVE_PARAMS[asset]

    def get_reserve_state(self, asset: str) -> ReserveState:
        return _RESERVE_STATES[asset]

    def get_liquidation_params(self, asset: str) -> LiquidationParams:
        return _LIQUIDATION_PARAMS[asset]

    def get_emode_category(self, category_id: int) -> EModeCategory:
        return _EMODE_CATEGORIES[category_id]

    def get_asset_price(self, asset: str) -> float:
        return _ASSET_PRICES[asset]

    def get_steth_eth_peg(self) -> float:
        return _STETH_ETH_PEG
