"""wstETH/ETH Risk Dashboard — Main Streamlit entry point."""

import os
from pathlib import Path

import streamlit as st

# Load .env file if present (for ETH_RPC_URL, etc.)
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

# Bridge Streamlit Cloud secrets into os.environ so the rest of the app
# (provider_factory, sidebar) can read them via os.environ.get().
try:
    for key in st.secrets:
        if isinstance(st.secrets[key], str):
            os.environ.setdefault(key, st.secrets[key])
except Exception:
    pass  # No secrets configured

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

    # Sidebar controls
    params = render_sidebar()

    # Build provider
    provider = create_provider(use_onchain=params.use_onchain_data)

    # Show data source and connection diagnostics
    if params.use_onchain_data:
        from src.data.onchain_provider import OnChainDataProvider

        if isinstance(provider, OnChainDataProvider):
            if provider.is_connected:
                st.sidebar.success("On-chain: connected")
                # Verify we can actually fetch data
                try:
                    test_peg = provider.get_steth_eth_peg()
                    st.sidebar.caption(f"Live stETH/ETH peg: {test_peg:.6f}")
                except Exception as exc:
                    st.sidebar.error(f"RPC call failed: {exc}")
            else:
                st.sidebar.error("On-chain: cannot reach RPC endpoint")
        else:
            # Diagnose why factory returned static provider
            diag = []
            rpc_url = os.environ.get("ETH_RPC_URL", "")
            if not rpc_url:
                diag.append("ETH_RPC_URL not found in environment")
                # Check if it's in st.secrets directly
                try:
                    secret_val = st.secrets.get("ETH_RPC_URL", "")
                    if secret_val:
                        diag.append(f"...but IS in st.secrets (bridge failed?)")
                    else:
                        diag.append("...also not in st.secrets")
                except Exception:
                    diag.append("...st.secrets not available")
            else:
                diag.append(f"ETH_RPC_URL is set ({rpc_url[:20]}...)")
            try:
                import web3  # noqa: F401
                diag.append("web3 is installed")
            except ImportError:
                diag.append("web3 is NOT installed")
                # Try to install at runtime and capture the error
                import subprocess
                try:
                    out = subprocess.check_output(
                        ["pip", "install", "web3>=6.0"],
                        stderr=subprocess.STDOUT,
                        timeout=120,
                    ).decode()
                    diag.append("pip install succeeded — reload the page")
                except subprocess.CalledProcessError as pip_err:
                    diag.append(f"pip install failed:\n{pip_err.output.decode()[-500:]}")
                except Exception as pip_exc:
                    diag.append(f"pip install error: {pip_exc}")
            # Try creating provider directly to capture the error
            try:
                from src.data.onchain_provider import OnChainDataProvider as _OCP
                if rpc_url:
                    _OCP(rpc_url=rpc_url)
                    diag.append("OnChainDataProvider created OK (should not reach here)")
            except ImportError as e:
                diag.append(f"Import error: {e}")
            except Exception as e:
                diag.append(f"Creation error: {e}")
            st.sidebar.error("Fell back to static data")
            for d in diag:
                st.sidebar.caption(d)

    # Refresh button for on-chain data
    if params.use_onchain_data and hasattr(provider, "refresh"):
        if st.sidebar.button("Refresh On-Chain Data"):
            provider.refresh()  # type: ignore[attr-defined]
            st.rerun()

    # Build position from sidebar params
    position = VaultPosition(
        collateral_amount=params.collateral_amount,
        debt_amount=params.debt_amount,
        emode_enabled=params.emode_enabled,
    )

    # If exchange rate factor is adjusted, scale the wstETH oracle price
    # proportionally.  This models a Lido slashing event reducing
    # stEthPerToken.  The oracle price already includes the current rate,
    # so we scale by (target / current).
    if params.depeg_level < 1.0:
        current_peg = provider.get_steth_eth_peg()
        peg_scale = params.depeg_level / current_peg if current_peg > 0 else params.depeg_level
        original_get_price = provider.get_asset_price
        original_get_peg = provider.get_steth_eth_peg

        def patched_price(asset: str) -> float:
            price = original_get_price(asset)
            if asset == "wstETH":
                return price * peg_scale
            return price

        def patched_peg() -> float:
            return params.depeg_level

        provider.get_asset_price = patched_price  # type: ignore[assignment]
        provider.get_steth_eth_peg = patched_peg  # type: ignore[assignment]

    # Tabs
    tab1, tab2, tab3, tab4, tab5 = st.tabs(
        [
            "Position Overview",
            "Interest Rates",
            "Liquidation Analysis",
            "Simulations",
            "Stress Tests",
        ]
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
