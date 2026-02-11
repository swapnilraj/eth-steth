"""Live on-chain integration tests — require ETH_RPC_URL and web3 installed."""

from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.onchain

RPC_URL = os.environ.get("ETH_RPC_URL", "")

if not RPC_URL:
    pytest.skip("ETH_RPC_URL not set", allow_module_level=True)

try:
    from web3 import Web3
except ImportError:
    pytest.skip("web3 not installed", allow_module_level=True)

from src.data.constants import WETH, WSTETH
from src.data.interfaces import LiquidationParams, ReserveParams, ReserveState
from src.data.onchain_provider import OnChainDataProvider
from src.data.provider_factory import create_provider
from src.protocol.emode import EModeCategory


@pytest.fixture(scope="module")
def provider() -> OnChainDataProvider:
    return OnChainDataProvider(rpc_url=RPC_URL, cache_ttl=300.0)


class TestConnection:
    def test_is_connected(self, provider: OnChainDataProvider):
        assert provider.is_connected is True


class TestReserveParams:
    def test_weth_reserve_params(self, provider: OnChainDataProvider):
        params = provider.get_reserve_params(WETH)
        assert isinstance(params, ReserveParams)
        assert 0 < params.optimal_utilization <= 1.0
        assert params.base_rate >= 0.0
        assert params.slope1 > 0.0
        assert params.slope2 > 0.0
        assert 0 < params.reserve_factor < 1.0

    def test_wsteth_reserve_params(self, provider: OnChainDataProvider):
        params = provider.get_reserve_params(WSTETH)
        assert isinstance(params, ReserveParams)
        assert 0 < params.optimal_utilization <= 1.0
        assert params.slope1 > 0.0


class TestReserveState:
    def test_weth_reserve_state(self, provider: OnChainDataProvider):
        state = provider.get_reserve_state(WETH)
        assert isinstance(state, ReserveState)
        assert state.total_supply > 0
        assert state.total_debt > 0
        assert state.total_debt <= state.total_supply

    def test_wsteth_reserve_state(self, provider: OnChainDataProvider):
        state = provider.get_reserve_state(WSTETH)
        assert isinstance(state, ReserveState)
        assert state.total_supply > 0


class TestLiquidationParams:
    def test_weth_liquidation_params(self, provider: OnChainDataProvider):
        params = provider.get_liquidation_params(WETH)
        assert isinstance(params, LiquidationParams)
        assert 0 < params.ltv < 1.0
        assert params.ltv < params.liquidation_threshold
        assert params.liquidation_bonus > 0

    def test_wsteth_liquidation_params(self, provider: OnChainDataProvider):
        params = provider.get_liquidation_params(WSTETH)
        assert isinstance(params, LiquidationParams)
        assert 0 < params.ltv < 1.0


class TestEMode:
    def test_eth_correlated_emode(self, provider: OnChainDataProvider):
        cat = provider.get_emode_category(1)
        assert isinstance(cat, EModeCategory)
        assert cat.category_id == 1
        assert cat.ltv > 0.9
        assert cat.liquidation_threshold > cat.ltv
        assert cat.liquidation_bonus > 0


class TestPrices:
    def test_weth_price_is_one(self, provider: OnChainDataProvider):
        price = provider.get_asset_price(WETH)
        assert isinstance(price, float)
        assert price == 1.0  # WETH/WETH = 1

    def test_wsteth_price_above_one(self, provider: OnChainDataProvider):
        price = provider.get_asset_price(WSTETH)
        assert isinstance(price, float)
        assert price > 1.0  # wstETH wraps staking rewards

    def test_steth_eth_peg_near_one(self, provider: OnChainDataProvider):
        peg = provider.get_steth_eth_peg()
        assert isinstance(peg, float)
        assert 0.95 < peg <= 1.01


class TestFactory:
    def test_create_onchain_provider(self):
        p = create_provider(use_onchain=True, rpc_url=RPC_URL)
        assert isinstance(p, OnChainDataProvider)
        state = p.get_reserve_state(WETH)
        assert state.total_supply > 0
