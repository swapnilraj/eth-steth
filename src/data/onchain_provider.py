"""On-chain data provider fetching live Aave V3 parameters via web3.py."""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

from src.data.constants import EMODE_ETH_CORRELATED, RAY, WETH, WSTETH
from src.data.contracts import (
    AAVE_ORACLE,
    AAVE_POOL,
    AAVE_POOL_DATA_PROVIDER,
    ASSET_ADDRESSES,
    CHAINLINK_FEED_ABI,
    CHAINLINK_STETH_ETH_FEED,
    ORACLE_ABI,
    POOL_ABI,
    POOL_DATA_PROVIDER_ABI,
    RATE_STRATEGY_ABI_V1,
    RATE_STRATEGY_ABI_V2,
    RATE_STRATEGY_ABI_V3,
)
from src.data.interfaces import (
    LiquidationParams,
    PoolDataProvider,
    ReserveParams,
    ReserveState,
)
from src.protocol.emode import EModeCategory

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# TTL cache
# ---------------------------------------------------------------------------

class _TTLCache:
    """Simple dict-based cache with per-entry TTL expiry."""

    def __init__(self, ttl: float) -> None:
        self._ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        ts, value = entry
        if time.monotonic() - ts > self._ttl:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic(), value)

    def clear(self) -> None:
        self._store.clear()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _bps_to_float(bps: int) -> float:
    """Convert basis points (1e4 scale) to a decimal fraction."""
    return bps / 10_000


def _ray_to_float(ray: int) -> float:
    """Convert RAY (1e27) fixed-point to a decimal fraction."""
    return ray / float(RAY)


# ---------------------------------------------------------------------------
# OnChainDataProvider
# ---------------------------------------------------------------------------

class OnChainDataProvider(PoolDataProvider):
    """Live on-chain data provider for Aave V3 via web3.py.

    Parameters
    ----------
    rpc_url : str
        Ethereum JSON-RPC endpoint URL.
    cache_ttl : float
        Seconds before a cached value expires (default 60).
    fallback : PoolDataProvider | None
        Optional fallback provider used when an RPC call fails.
    """

    def __init__(
        self,
        rpc_url: str,
        cache_ttl: float = 60.0,
        fallback: PoolDataProvider | None = None,
    ) -> None:
        from web3 import Web3

        self._w3 = Web3(Web3.HTTPProvider(rpc_url))
        self._cache = _TTLCache(cache_ttl)
        self._fallback = fallback

        # Pre-build main contract objects (no RPC calls here)
        self._pool_data_provider = self._w3.eth.contract(
            address=self._w3.to_checksum_address(AAVE_POOL_DATA_PROVIDER),
            abi=POOL_DATA_PROVIDER_ABI,
        )
        self._pool = self._w3.eth.contract(
            address=self._w3.to_checksum_address(AAVE_POOL),
            abi=POOL_ABI,
        )
        self._oracle = self._w3.eth.contract(
            address=self._w3.to_checksum_address(AAVE_ORACLE),
            abi=ORACLE_ABI,
        )
        self._chainlink_feed = self._w3.eth.contract(
            address=self._w3.to_checksum_address(CHAINLINK_STETH_ETH_FEED),
            abi=CHAINLINK_FEED_ABI,
        )

        # Lazily resolved per-asset rate strategy contracts
        self._rate_strategy_contracts: dict[str, Any] = {}

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_address(self, asset: str) -> str:
        """Map asset symbol to checksummed on-chain address."""
        raw = ASSET_ADDRESSES.get(asset)
        if raw is None:
            raise ValueError(f"Unknown asset: {asset}")
        return self._w3.to_checksum_address(raw)

    def _get_rate_strategy_contract(self, asset: str) -> Any:
        """Lazily fetch and cache the rate strategy contract for *asset*."""
        if asset in self._rate_strategy_contracts:
            return self._rate_strategy_contracts[asset]

        addr = self._pool_data_provider.functions.getInterestRateStrategyAddress(
            self._resolve_address(asset),
        ).call()

        # Build with all ABIs (v3.2 + v3.0 struct + v1 individual getters)
        contract = self._w3.eth.contract(
            address=self._w3.to_checksum_address(addr),
            abi=RATE_STRATEGY_ABI_V3 + RATE_STRATEGY_ABI_V2 + RATE_STRATEGY_ABI_V1,
        )
        self._rate_strategy_contracts[asset] = contract
        return contract

    def _call_with_fallback(
        self,
        cache_key: str,
        fetcher: Callable[[], Any],
        fallback_method: Callable[..., Any] | None,
        *fallback_args: Any,
    ) -> Any:
        """Cache → RPC → fallback pipeline."""
        # 1. Cache hit
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        # 2. RPC call
        try:
            value = fetcher()
            self._cache.set(cache_key, value)
            return value
        except Exception:
            logger.warning(
                "RPC call failed for key=%s, using fallback", cache_key, exc_info=True
            )

        # 3. Fallback
        if fallback_method is not None:
            return fallback_method(*fallback_args)

        raise RuntimeError(f"RPC call failed and no fallback available for {cache_key}")

    # ------------------------------------------------------------------
    # Rate strategy fetching (v2 struct with v1 fallback)
    # ------------------------------------------------------------------

    def _fetch_rate_params(self, asset: str) -> ReserveParams:
        """Fetch interest rate params from the on-chain rate strategy."""
        strategy = self._get_rate_strategy_contract(asset)
        asset_addr = self._resolve_address(asset)

        # Reserve factor from PoolDataProvider
        config = self._pool_data_provider.functions.getReserveConfigurationData(
            asset_addr,
        ).call()
        reserve_factor = _bps_to_float(config[4])

        # Try V3.2: getInterestRateDataBps(address reserve) — bps values
        try:
            data = strategy.functions.getInterestRateDataBps(asset_addr).call()
            return ReserveParams(
                optimal_utilization=data[0] / 100 / 100,  # uint16 bps (e.g. 9400 → 0.94)
                base_rate=data[1] / 100 / 100,  # uint32 bps
                slope1=data[2] / 100 / 100,
                slope2=data[3] / 100 / 100,
                reserve_factor=reserve_factor,
            )
        except Exception:
            pass

        # Try V3.0/V3.1: getInterestRateData() — bps values
        try:
            data = strategy.functions.getInterestRateData().call()
            return ReserveParams(
                optimal_utilization=_bps_to_float(data[0]),
                base_rate=_bps_to_float(data[1]),
                slope1=_bps_to_float(data[2]),
                slope2=_bps_to_float(data[3]),
                reserve_factor=reserve_factor,
            )
        except Exception:
            pass

        # Fall back to V1 individual RAY-returning getters
        optimal = _ray_to_float(strategy.functions.OPTIMAL_USAGE_RATIO().call())
        base = _ray_to_float(strategy.functions.getBaseVariableBorrowRate().call())
        s1 = _ray_to_float(strategy.functions.getVariableRateSlope1().call())
        s2 = _ray_to_float(strategy.functions.getVariableRateSlope2().call())

        return ReserveParams(
            optimal_utilization=optimal,
            base_rate=base,
            slope1=s1,
            slope2=s2,
            reserve_factor=reserve_factor,
        )

    # ------------------------------------------------------------------
    # PoolDataProvider interface
    # ------------------------------------------------------------------

    def get_reserve_params(self, asset: str) -> ReserveParams:
        fb = self._fallback.get_reserve_params if self._fallback else None
        return self._call_with_fallback(
            f"reserve_params:{asset}", lambda: self._fetch_rate_params(asset), fb, asset
        )

    def get_reserve_state(self, asset: str) -> ReserveState:
        def _fetch() -> ReserveState:
            asset_addr = self._resolve_address(asset)
            data = self._pool_data_provider.functions.getReserveData(asset_addr).call()
            total_supply = data[2] / 1e18  # totalAToken
            total_debt = data[4] / 1e18  # totalVariableDebt
            return ReserveState(total_supply=total_supply, total_debt=total_debt)

        fb = self._fallback.get_reserve_state if self._fallback else None
        return self._call_with_fallback(f"reserve_state:{asset}", _fetch, fb, asset)

    def get_liquidation_params(self, asset: str) -> LiquidationParams:
        def _fetch() -> LiquidationParams:
            asset_addr = self._resolve_address(asset)
            config = self._pool_data_provider.functions.getReserveConfigurationData(
                asset_addr,
            ).call()
            ltv = _bps_to_float(config[1])
            liq_threshold = _bps_to_float(config[2])
            # Aave stores liquidation bonus as 10000 + bonus_bps
            liq_bonus = (config[3] - 10_000) / 10_000
            return LiquidationParams(
                ltv=ltv,
                liquidation_threshold=liq_threshold,
                liquidation_bonus=liq_bonus,
            )

        fb = self._fallback.get_liquidation_params if self._fallback else None
        return self._call_with_fallback(
            f"liquidation_params:{asset}", _fetch, fb, asset
        )

    def get_emode_category(self, category_id: int) -> EModeCategory:
        def _fetch() -> EModeCategory:
            data = self._pool.functions.getEModeCategoryData(category_id).call()
            return EModeCategory(
                category_id=category_id,
                label=data[4] if data[4] else "ETH correlated",
                ltv=_bps_to_float(data[0]),
                liquidation_threshold=_bps_to_float(data[1]),
                liquidation_bonus=(data[2] - 10_000) / 10_000,
            )

        fb = self._fallback.get_emode_category if self._fallback else None
        return self._call_with_fallback(
            f"emode:{category_id}", _fetch, fb, category_id
        )

    def get_asset_price(self, asset: str) -> float:
        def _fetch() -> float:
            asset_addr = self._resolve_address(asset)
            weth_addr = self._resolve_address(WETH)
            base_unit = self._oracle.functions.BASE_CURRENCY_UNIT().call()
            asset_price = self._oracle.functions.getAssetPrice(asset_addr).call()
            weth_price = self._oracle.functions.getAssetPrice(weth_addr).call()
            # Normalize to ETH terms
            return asset_price / weth_price

        fb = self._fallback.get_asset_price if self._fallback else None
        return self._call_with_fallback(f"price:{asset}", _fetch, fb, asset)

    def get_steth_eth_peg(self) -> float:
        def _fetch() -> float:
            decimals = self._chainlink_feed.functions.decimals().call()
            round_data = self._chainlink_feed.functions.latestRoundData().call()
            answer = round_data[1]
            return answer / (10**decimals)

        fb = self._fallback.get_steth_eth_peg if self._fallback else None
        return self._call_with_fallback("steth_eth_peg", _fetch, fb)

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        """Invalidate all cached values, forcing fresh RPC calls."""
        self._cache.clear()
        self._rate_strategy_contracts.clear()

    @property
    def is_connected(self) -> bool:
        """Check if the Web3 provider is connected."""
        try:
            return self._w3.is_connected()
        except Exception:
            return False
