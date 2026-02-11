"""Tests for OnChainDataProvider — unit conversions, mock integration, interface conformance."""

from __future__ import annotations

import math
import sys
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Install a mock 'web3' module so we can import OnChainDataProvider without
# having the real web3 package installed.
# ---------------------------------------------------------------------------
_mock_web3_mod = MagicMock()
_MockWeb3Class = MagicMock()
_mock_web3_mod.Web3 = _MockWeb3Class
sys.modules.setdefault("web3", _mock_web3_mod)

from src.data.constants import RAY, WETH, WSTETH  # noqa: E402
from src.data.contracts import ASSET_ADDRESSES  # noqa: E402
from src.data.interfaces import (  # noqa: E402
    LiquidationParams,
    PoolDataProvider,
    ReserveParams,
    ReserveState,
)
from src.data.onchain_provider import (  # noqa: E402
    OnChainDataProvider,
    _TTLCache,
    _bps_to_float,
    _ray_to_float,
)
from src.data.provider_factory import create_provider  # noqa: E402
from src.data.static_params import StaticDataProvider  # noqa: E402
from src.protocol.emode import EModeCategory  # noqa: E402


# ======================================================================
# 1. Unit conversion tests
# ======================================================================


class TestUnitConversions:
    """Pure math — no mocking required."""

    def test_bps_to_float_zero(self):
        assert _bps_to_float(0) == 0.0

    def test_bps_to_float_half(self):
        assert _bps_to_float(5_000) == 0.5

    def test_bps_to_float_full(self):
        assert _bps_to_float(10_000) == 1.0

    def test_bps_to_float_ltv(self):
        assert math.isclose(_bps_to_float(8050), 0.805)

    def test_bps_to_float_threshold(self):
        assert math.isclose(_bps_to_float(9550), 0.955)

    def test_ray_to_float_zero(self):
        assert _ray_to_float(0) == 0.0

    def test_ray_to_float_one(self):
        assert math.isclose(_ray_to_float(RAY), 1.0)

    def test_ray_to_float_slope(self):
        slope_ray = 27 * 10**24  # 0.027 * 1e27
        assert math.isclose(_ray_to_float(slope_ray), 0.027, rel_tol=1e-9)

    def test_ray_to_float_optimal_utilization(self):
        optimal_ray = 92 * 10**25
        assert math.isclose(_ray_to_float(optimal_ray), 0.92, rel_tol=1e-9)

    def test_liquidation_bonus_encoding(self):
        """Aave stores bonus as 10000 + bonus_bps."""
        raw_bonus = 10_500  # 5% bonus
        decoded = (raw_bonus - 10_000) / 10_000
        assert math.isclose(decoded, 0.05)

    def test_liquidation_bonus_encoding_emode(self):
        raw_bonus = 10_100  # 1% bonus
        decoded = (raw_bonus - 10_000) / 10_000
        assert math.isclose(decoded, 0.01)

    def test_price_normalization(self):
        """Oracle prices normalized to ETH = asset_price / weth_price."""
        wsteth_price = 1_180_000_000
        weth_price = 1_000_000_000
        ratio = wsteth_price / weth_price
        assert math.isclose(ratio, 1.18)

    def test_chainlink_answer_conversion(self):
        """Chainlink answer / 10^decimals."""
        answer = 99850000  # ~0.9985
        decimals = 8
        peg = answer / (10**decimals)
        assert math.isclose(peg, 0.9985, rel_tol=1e-6)

    def test_token_amount_conversion(self):
        """18-decimal token amounts to float."""
        raw = 2_800_000 * 10**18
        converted = raw / 1e18
        assert math.isclose(converted, 2_800_000.0)


# ======================================================================
# 2. TTL cache tests
# ======================================================================


class TestTTLCache:
    def test_set_and_get(self):
        cache = _TTLCache(ttl=60.0)
        cache.set("key", "value")
        assert cache.get("key") == "value"

    def test_miss_returns_none(self):
        cache = _TTLCache(ttl=60.0)
        assert cache.get("missing") is None

    def test_expired_entry(self):
        cache = _TTLCache(ttl=0.0)  # Immediate expiry
        cache.set("key", "value")
        assert cache.get("key") is None

    def test_clear(self):
        cache = _TTLCache(ttl=60.0)
        cache.set("a", 1)
        cache.set("b", 2)
        cache.clear()
        assert cache.get("a") is None
        assert cache.get("b") is None


# ======================================================================
# 3. Mock-based integration tests
# ======================================================================


def _make_provider(**kwargs) -> OnChainDataProvider:
    """Create an OnChainDataProvider then replace internals with mocks.

    Works whether web3 is real or mocked in sys.modules.
    """
    mock_w3 = MagicMock()
    mock_w3.is_connected.return_value = True
    mock_w3.to_checksum_address = lambda addr: addr

    def _make_contract(address, abi):
        contract = MagicMock()
        contract.address = address
        return contract

    mock_w3.eth.contract = MagicMock(side_effect=_make_contract)

    # Temporarily force our mock into sys.modules so __init__ uses it
    real_web3 = sys.modules.get("web3")
    mock_mod = MagicMock()
    mock_mod.Web3 = MagicMock(return_value=mock_w3)
    mock_mod.Web3.HTTPProvider = MagicMock()
    sys.modules["web3"] = mock_mod

    try:
        provider = OnChainDataProvider(rpc_url="http://localhost:8545", **kwargs)
    finally:
        # Restore whatever was there before
        if real_web3 is not None:
            sys.modules["web3"] = real_web3
        else:
            sys.modules.pop("web3", None)

    return provider


class TestOnChainProviderMocked:
    """Full integration flow with mocked Web3."""

    def test_get_reserve_state(self):
        provider = _make_provider()

        total_atoken = 2_800_000 * 10**18
        total_var_debt = 2_200_000 * 10**18
        reserve_data = (0, 0, total_atoken, 0, total_var_debt, 0, 0, 0, 0, 0, 0, 0)
        provider._pool_data_provider.functions.getReserveData.return_value.call.return_value = reserve_data

        state = provider.get_reserve_state(WETH)
        assert isinstance(state, ReserveState)
        assert math.isclose(state.total_supply, 2_800_000.0)
        assert math.isclose(state.total_debt, 2_200_000.0)

    def test_get_liquidation_params(self):
        provider = _make_provider()

        config_data = (18, 8050, 8300, 10_500, 1500, True, True, False, True, False)
        provider._pool_data_provider.functions.getReserveConfigurationData.return_value.call.return_value = config_data

        params = provider.get_liquidation_params(WETH)
        assert isinstance(params, LiquidationParams)
        assert math.isclose(params.ltv, 0.805)
        assert math.isclose(params.liquidation_threshold, 0.83)
        assert math.isclose(params.liquidation_bonus, 0.05)

    def test_get_emode_category(self):
        provider = _make_provider()

        emode_data = (9350, 9550, 10_100, "0x" + "0" * 40, "ETH correlated")
        provider._pool.functions.getEModeCategoryData.return_value.call.return_value = emode_data

        cat = provider.get_emode_category(1)
        assert isinstance(cat, EModeCategory)
        assert cat.category_id == 1
        assert math.isclose(cat.ltv, 0.935)
        assert math.isclose(cat.liquidation_threshold, 0.955)
        assert math.isclose(cat.liquidation_bonus, 0.01)
        assert cat.label == "ETH correlated"

    def test_get_asset_price(self):
        provider = _make_provider()

        provider._oracle.functions.BASE_CURRENCY_UNIT.return_value.call.return_value = 10**8
        # Two sequential calls: first for wstETH, then for WETH
        provider._oracle.functions.getAssetPrice.return_value.call.side_effect = [
            118_000_000,  # wstETH
            100_000_000,  # WETH
        ]

        price = provider.get_asset_price(WSTETH)
        assert math.isclose(price, 1.18)

    def test_get_steth_eth_peg(self):
        provider = _make_provider()

        provider._chainlink_feed.functions.decimals.return_value.call.return_value = 18
        provider._chainlink_feed.functions.latestRoundData.return_value.call.return_value = (
            1, 999_500_000_000_000_000, 0, 0, 0,
        )

        peg = provider.get_steth_eth_peg()
        assert math.isclose(peg, 0.9995, rel_tol=1e-6)

    def test_get_reserve_params_v32_bps(self):
        """V3.2 path: getInterestRateDataBps(address) with bps values."""
        provider = _make_provider()

        rate_contract = MagicMock()
        # V3.2: (optimalUsageRatio, baseVariableBorrowRate, slope1, slope2)
        # Values are in "percent bps" — e.g. 9200 = 92.00%
        rate_contract.functions.getInterestRateDataBps.return_value.call.return_value = (
            9200, 0, 270, 4000,
        )
        config_data = (18, 8050, 8300, 10_500, 1500, True, True, False, True, False)
        provider._pool_data_provider.functions.getReserveConfigurationData.return_value.call.return_value = config_data
        provider._get_rate_strategy_contract = MagicMock(return_value=rate_contract)

        params = provider.get_reserve_params(WETH)
        assert isinstance(params, ReserveParams)
        assert math.isclose(params.optimal_utilization, 0.92)
        assert math.isclose(params.base_rate, 0.0)
        assert math.isclose(params.slope1, 0.027)
        assert math.isclose(params.slope2, 0.40)
        assert math.isclose(params.reserve_factor, 0.15)

    def test_get_reserve_params_v1_fallback(self):
        """V1 path: individual RAY-returning getters (V3.2 and V3.0 fail)."""
        provider = _make_provider()

        rate_contract = MagicMock()
        # V3.2 fails
        rate_contract.functions.getInterestRateDataBps.return_value.call.side_effect = Exception("not supported")
        # V3.0 fails
        rate_contract.functions.getInterestRateData.return_value.call.side_effect = Exception("not supported")
        # V1 individual getters succeed
        rate_contract.functions.OPTIMAL_USAGE_RATIO.return_value.call.return_value = 92 * 10**25
        rate_contract.functions.getBaseVariableBorrowRate.return_value.call.return_value = 0
        rate_contract.functions.getVariableRateSlope1.return_value.call.return_value = 27 * 10**24
        rate_contract.functions.getVariableRateSlope2.return_value.call.return_value = 40 * 10**25

        config_data = (18, 8050, 8300, 10_500, 1500, True, True, False, True, False)
        provider._pool_data_provider.functions.getReserveConfigurationData.return_value.call.return_value = config_data
        provider._get_rate_strategy_contract = MagicMock(return_value=rate_contract)

        params = provider.get_reserve_params(WETH)
        assert math.isclose(params.optimal_utilization, 0.92, rel_tol=1e-9)
        assert math.isclose(params.base_rate, 0.0)
        assert math.isclose(params.slope1, 0.027, rel_tol=1e-9)
        assert math.isclose(params.slope2, 0.40, rel_tol=1e-9)
        assert math.isclose(params.reserve_factor, 0.15)

    def test_fallback_on_rpc_failure(self):
        fallback = StaticDataProvider()
        provider = _make_provider(fallback=fallback)

        provider._pool_data_provider.functions.getReserveData.return_value.call.side_effect = Exception("RPC error")

        state = provider.get_reserve_state(WETH)
        expected = fallback.get_reserve_state(WETH)
        assert state == expected

    def test_caching(self):
        provider = _make_provider()

        total_atoken = 2_800_000 * 10**18
        total_var_debt = 2_200_000 * 10**18
        reserve_data = (0, 0, total_atoken, 0, total_var_debt, 0, 0, 0, 0, 0, 0, 0)
        call_mock = provider._pool_data_provider.functions.getReserveData.return_value.call
        call_mock.return_value = reserve_data

        provider.get_reserve_state(WETH)
        assert call_mock.call_count == 1

        provider.get_reserve_state(WETH)
        assert call_mock.call_count == 1

    def test_refresh_clears_cache(self):
        provider = _make_provider()

        total_atoken = 2_800_000 * 10**18
        total_var_debt = 2_200_000 * 10**18
        reserve_data = (0, 0, total_atoken, 0, total_var_debt, 0, 0, 0, 0, 0, 0, 0)
        call_mock = provider._pool_data_provider.functions.getReserveData.return_value.call
        call_mock.return_value = reserve_data

        provider.get_reserve_state(WETH)
        assert call_mock.call_count == 1

        provider.refresh()
        provider.get_reserve_state(WETH)
        assert call_mock.call_count == 2

    def test_is_connected(self):
        provider = _make_provider()
        provider._w3.is_connected.return_value = True
        assert provider.is_connected is True

        provider._w3.is_connected.return_value = False
        assert provider.is_connected is False


# ======================================================================
# 4. Interface conformance tests
# ======================================================================


class TestInterfaceConformance:
    def test_static_is_pool_data_provider(self):
        assert isinstance(StaticDataProvider(), PoolDataProvider)

    def test_onchain_is_pool_data_provider(self):
        provider = _make_provider()
        assert isinstance(provider, PoolDataProvider)

    def test_static_returns_correct_types(self):
        p = StaticDataProvider()
        assert isinstance(p.get_reserve_params(WETH), ReserveParams)
        assert isinstance(p.get_reserve_state(WETH), ReserveState)
        assert isinstance(p.get_liquidation_params(WETH), LiquidationParams)
        assert isinstance(p.get_emode_category(1), EModeCategory)
        assert isinstance(p.get_asset_price(WETH), float)
        assert isinstance(p.get_steth_eth_peg(), float)


# ======================================================================
# 5. Provider factory tests
# ======================================================================


class TestProviderFactory:
    def test_static_by_default(self):
        provider = create_provider(use_onchain=False)
        assert isinstance(provider, StaticDataProvider)

    @patch.dict("os.environ", {}, clear=True)
    def test_onchain_without_url_falls_back(self):
        provider = create_provider(use_onchain=True, rpc_url=None)
        assert isinstance(provider, StaticDataProvider)

    def test_onchain_with_url(self):
        # The mock web3 module is in sys.modules, so this should succeed
        provider = create_provider(use_onchain=True, rpc_url="http://localhost:8545")
        assert isinstance(provider, OnChainDataProvider)

    @patch.dict("os.environ", {"ETH_RPC_URL": ""})
    def test_empty_env_var_falls_back(self):
        provider = create_provider(use_onchain=True)
        assert isinstance(provider, StaticDataProvider)
