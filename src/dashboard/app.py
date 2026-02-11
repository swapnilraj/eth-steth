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

from src.dashboard.components.sidebar import render_sidebar
from src.dashboard.pages.liquidation import render_liquidation
from src.dashboard.pages.overview import render_overview
from src.dashboard.pages.rates import render_rates
from src.dashboard.pages.simulations import render_simulations
from src.dashboard.pages.stress_tests import render_stress_tests
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

    # Refresh button for on-chain data
    if params.use_onchain_data and hasattr(provider, "refresh"):
        if st.button("Refresh On-Chain Data"):
            provider.refresh()  # type: ignore[attr-defined]
            st.rerun()

    # Build position from sidebar params
    position = VaultPosition(
        collateral_amount=params.collateral_amount,
        debt_amount=params.debt_amount,
        emode_enabled=params.emode_enabled,
    )

    # If depeg is adjusted, we need a modified provider
    # For simplicity, we monkey-patch the peg value
    if params.depeg_level < 1.0:
        original_peg = provider.get_steth_eth_peg

        def patched_peg() -> float:
            return params.depeg_level

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
