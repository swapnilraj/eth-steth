"""Sidebar parameter controls."""

from dataclasses import dataclass

import streamlit as st


@dataclass
class SidebarParams:
    """User-controlled parameters from the sidebar."""

    collateral_amount: float
    debt_amount: float
    emode_enabled: bool
    utilization_override: float | None
    depeg_level: float
    staking_apy: float
    use_onchain_data: bool = False


def render_sidebar() -> SidebarParams:
    """Render sidebar controls and return selected parameters."""
    st.sidebar.header("Data Source")

    use_onchain = st.sidebar.checkbox("Use On-Chain Data", value=False)
    if use_onchain:
        try:
            from src.data.onchain_provider import OnChainDataProvider

            import os

            rpc_url = os.environ.get("ETH_RPC_URL", "")
            if rpc_url:
                st.sidebar.caption("RPC: connected")
            else:
                st.sidebar.caption("RPC: no ETH_RPC_URL set — will use static fallback")
        except ImportError:
            st.sidebar.caption("web3 not installed — will use static fallback")

    st.sidebar.header("Position Parameters")

    collateral = st.sidebar.number_input(
        "wstETH Collateral",
        min_value=0.0,
        value=12_000.0,
        step=100.0,
        format="%.0f",
    )

    debt = st.sidebar.number_input(
        "WETH Debt",
        min_value=0.0,
        value=10_500.0,
        step=100.0,
        format="%.0f",
    )

    emode = st.sidebar.checkbox("E-mode Enabled", value=True)

    st.sidebar.header("What-If Analysis")

    use_util_override = st.sidebar.checkbox("Override WETH Utilization", value=False)
    util_override: float | None = None
    if use_util_override:
        util_override = (
            st.sidebar.slider(
                "WETH Utilization (%)",
                min_value=0,
                max_value=100,
                value=78,
            )
            / 100.0
        )

    depeg = st.sidebar.slider(
        "stETH/ETH Peg",
        min_value=0.85,
        max_value=1.00,
        value=1.00,
        step=0.005,
        format="%.3f",
    )

    staking_apy = st.sidebar.slider(
        "Staking APY (%)",
        min_value=0.0,
        max_value=10.0,
        value=3.5,
        step=0.1,
    ) / 100.0

    return SidebarParams(
        collateral_amount=collateral,
        debt_amount=debt,
        emode_enabled=emode,
        utilization_override=util_override,
        depeg_level=depeg,
        staking_apy=staking_apy,
        use_onchain_data=use_onchain,
    )
