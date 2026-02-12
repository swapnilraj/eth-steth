"""wstETH/ETH Risk Dashboard — Main Streamlit entry point."""

import importlib
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Dependency bootstrap — Streamlit Cloud's read-only venv may not include
# web3 even when listed in requirements.txt / pyproject.toml.  Install to
# a writable /tmp directory as a fallback.
# ---------------------------------------------------------------------------
_WEB3_LIB = "/tmp/web3_packages"  # noqa: S108
if os.path.isdir(_WEB3_LIB):
    sys.path.insert(0, _WEB3_LIB)
try:
    import web3 as _web3_check  # noqa: F401
except ImportError:
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install",
         "--target", _WEB3_LIB, "web3>=6.0"],
        timeout=300,
    )
    sys.path.insert(0, _WEB3_LIB)
    for _mod in list(sys.modules):
        if _mod == "web3" or _mod.startswith("web3."):
            del sys.modules[_mod]
    importlib.invalidate_caches()
    import web3 as _web3_check  # noqa: F401

import streamlit as st

# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

# Load .env file if present (local development)
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# Bridge Streamlit Cloud secrets into os.environ
try:
    for key in st.secrets:
        if isinstance(st.secrets[key], str):
            os.environ.setdefault(key, st.secrets[key])
except Exception:
    pass  # No secrets configured

# ---------------------------------------------------------------------------
# Imports
# ---------------------------------------------------------------------------

from src.dashboard.components.sidebar import render_sidebar
from src.dashboard.tabs.liquidation import render_liquidation
from src.dashboard.tabs.overview import render_overview
from src.dashboard.tabs.rates import render_rates
from src.dashboard.tabs.simulations import render_simulations
from src.dashboard.tabs.stress_tests import render_stress_tests
from src.data.provider_factory import create_provider
from src.position.vault_position import VaultPosition


def main() -> None:
    st.set_page_config(
        page_title="wstETH/ETH Risk Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("wstETH/ETH Risk Dashboard")
    st.caption("Aave V3 — Mellow Vault Position Analysis")

    # ------------------------------------------------------------------
    # Data source toggle + provider
    # ------------------------------------------------------------------
    use_onchain = st.sidebar.checkbox(
        "Use On-Chain Data", value=False, key="use_onchain",
    )
    provider = create_provider(use_onchain=use_onchain)

    # Connection status
    if use_onchain:
        from src.data.onchain_provider import OnChainDataProvider

        if isinstance(provider, OnChainDataProvider):
            if provider.is_connected:
                st.sidebar.success("On-chain: connected")
                try:
                    peg = provider.get_steth_eth_peg()
                    st.sidebar.caption(f"Live stETH/ETH peg: {peg:.6f}")
                except Exception as exc:
                    st.sidebar.error(f"RPC call failed: {exc}")
            else:
                st.sidebar.error("On-chain: cannot reach RPC endpoint")
        else:
            rpc = os.environ.get("ETH_RPC_URL", "")
            if not rpc:
                st.sidebar.warning("ETH_RPC_URL not set — using static data")
            else:
                st.sidebar.warning("On-chain provider failed — using static data")

    # Refresh button
    if use_onchain and hasattr(provider, "refresh"):
        if st.sidebar.button("Refresh On-Chain Data"):
            provider.refresh()  # type: ignore[attr-defined]
            st.rerun()

    # ------------------------------------------------------------------
    # Staking APY from provider (with direct Lido API fallback)
    # ------------------------------------------------------------------
    live_staking_apy: float | None = None
    try:
        apy = provider.get_staking_apy()
        if use_onchain or abs(apy - 0.035) > 0.0001:
            live_staking_apy = apy
    except Exception:
        pass

    # If the provider returned the static default, try the Lido API directly
    if use_onchain and (live_staking_apy is None or abs(live_staking_apy - 0.035) < 0.0001):
        try:
            import requests as _req

            resp = _req.get(
                "https://eth-api.lido.fi/v1/protocol/steth/apr/sma",
                timeout=10,
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
            live_staking_apy = float(resp.json()["data"]["smaApr"]) / 100.0
        except Exception as exc:
            st.sidebar.warning(f"Could not fetch live staking APY: {exc}")

    # ------------------------------------------------------------------
    # Sidebar controls
    # ------------------------------------------------------------------
    params = render_sidebar(live_staking_apy=live_staking_apy)

    position = VaultPosition(
        collateral_amount=params.collateral_amount,
        debt_amount=params.debt_amount,
        emode_enabled=params.emode_enabled,
    )

    # Exchange-rate override (models Lido slashing)
    if params.depeg_level < 1.0:
        current_peg = provider.get_steth_eth_peg()
        peg_scale = params.depeg_level / current_peg if current_peg > 0 else params.depeg_level
        original_get_price = provider.get_asset_price

        def patched_price(asset: str) -> float:
            price = original_get_price(asset)
            if asset == "wstETH":
                return price * peg_scale
            return price

        def patched_peg() -> float:
            return params.depeg_level

        provider.get_asset_price = patched_price  # type: ignore[assignment]
        provider.get_steth_eth_peg = patched_peg  # type: ignore[assignment]

    # ------------------------------------------------------------------
    # Tabs
    # ------------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        ["Position Overview", "Interest Rates", "Liquidation Analysis",
         "Simulations", "Stress Tests"],
    )

    with tab1:
        render_overview(position, provider, params.staking_apy)
    with tab2:
        render_rates(provider, params.utilization_override)
    with tab3:
        render_liquidation(position, provider)
    with tab4:
        render_simulations(position, provider, params.staking_apy)
    with tab5:
        render_stress_tests(position, provider, params.staking_apy)


if __name__ == "__main__":
    main()
