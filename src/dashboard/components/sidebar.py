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


def render_sidebar(live_staking_apy: float | None = None) -> SidebarParams:
    """Render sidebar controls and return selected parameters.

    Parameters
    ----------
    live_staking_apy : float | None
        If provided, used as the default staking APY value (from on-chain).
    """
    # "Data Source" header and on-chain toggle are rendered in app.py
    # before this function is called (to fetch live staking APY first).

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
        "wstETH Exchange Rate Factor",
        min_value=0.85,
        max_value=1.00,
        value=1.00,
        step=0.005,
        format="%.3f",
    )
    st.sidebar.caption(
        "Models a reduction in wstETH's protocol exchange rate "
        "(e.g. Lido slashing). Aave V3 uses a hardcoded 1:1 stETH/ETH "
        "oracle, so secondary-market depegs do not affect health factors."
    )

    default_apy = round(live_staking_apy * 100, 1) if live_staking_apy is not None else 3.5
    staking_apy = st.sidebar.slider(
        "Staking APY (%)",
        min_value=0.0,
        max_value=10.0,
        value=default_apy,
        step=0.1,
    ) / 100.0
    if live_staking_apy is not None:
        st.sidebar.caption(f"Default from Lido: {live_staking_apy*100:.2f}%")

    return SidebarParams(
        collateral_amount=collateral,
        debt_amount=debt,
        emode_enabled=emode,
        utilization_override=util_override,
        depeg_level=depeg,
        staking_apy=staking_apy,
    )
