"""Position Overview page — KPI cards and position summary."""

import streamlit as st

from src.dashboard.components.metrics_cards import kpi_row
from src.data.interfaces import PoolDataProvider
from src.position.pnl import compute_apy_breakdown, daily_pnl
from src.position.vault_position import VaultPosition


def render_overview(
    position: VaultPosition,
    provider: PoolDataProvider,
    staking_apy: float,
) -> None:
    """Render the position overview page."""
    st.header("Position Overview")

    hf = position.health_factor(provider)
    leverage = position.leverage_with_prices(provider)
    collateral_val = position.collateral_value(provider)
    debt_val = position.debt_value(provider)
    net_val = position.net_value(provider)
    breakdown = compute_apy_breakdown(position, provider, staking_apy)
    daily = daily_pnl(position, provider, staking_apy)

    # Health factor status
    if hf >= 1.5:
        hf_display = f"{hf:.3f}"
    elif hf >= 1.1:
        hf_display = f"{hf:.3f}"
    else:
        hf_display = f"{hf:.3f}"

    # KPI row 1: Core metrics
    kpi_row(
        [
            ("Health Factor", hf_display, None),
            ("Net APY", f"{breakdown.net_apy*100:.2f}%", None),
            ("Leverage", f"{leverage:.2f}x", None),
            ("Daily P&L", f"{daily:.2f} ETH", None),
        ]
    )

    st.divider()

    # KPI row 2: Position values
    kpi_row(
        [
            ("Collateral (wstETH)", f"{position.collateral_amount:,.0f}", f"{collateral_val:,.1f} ETH"),
            ("Debt (WETH)", f"{position.debt_amount:,.0f}", f"{debt_val:,.1f} ETH"),
            ("Net Equity", f"{net_val:,.1f} ETH", None),
        ]
    )

    st.divider()

    # APY breakdown
    st.subheader("APY Breakdown")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Staking APY", f"{breakdown.staking_apy*100:.2f}%")
    with col2:
        st.metric("Supply APY", f"{breakdown.supply_apy*100:.4f}%")
    with col3:
        st.metric("Borrow APY", f"-{breakdown.borrow_apy*100:.2f}%")

    # Peg display
    peg = provider.get_steth_eth_peg()
    st.info(f"stETH/ETH Peg: **{peg:.4f}**")
