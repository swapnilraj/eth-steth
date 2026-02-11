"""Liquidation Analysis page — health factor, depeg sensitivity, distance-to-liquidation."""

import pandas as pd
import streamlit as st

from src.dashboard.components.charts import depeg_sensitivity_chart, health_factor_gauge
from src.data.constants import WSTETH
from src.data.interfaces import PoolDataProvider
from src.position.vault_position import VaultPosition


def render_liquidation(
    position: VaultPosition,
    provider: PoolDataProvider,
) -> None:
    """Render the liquidation analysis page."""
    st.header("Liquidation Analysis")

    liq_model = position.get_liquidation_model(provider)
    collateral_val = position.collateral_value(provider)
    debt_val = position.debt_value(provider)
    hf = liq_model.health_factor(collateral_val, debt_val)
    # The oracle price already includes the stETH/ETH peg. For depeg
    # sensitivity analysis we need the exchange-rate-only price (peg
    # factored out), so that LiquidationModel.depeg_sensitivity can
    # multiply by the stressed peg without double-counting.
    current_peg = provider.get_steth_eth_peg()
    wsteth_oracle_price = provider.get_asset_price(WSTETH)
    wsteth_exchange_rate = wsteth_oracle_price / current_peg if current_peg > 0 else wsteth_oracle_price

    # Health factor gauge
    col1, col2 = st.columns([1, 1])

    with col1:
        fig_gauge = health_factor_gauge(hf)
        st.plotly_chart(fig_gauge, use_container_width=True)

    with col2:
        st.subheader("Position Safety")
        close = liq_model.close_factor(hf)
        drop = liq_model.liquidation_price_drop(collateral_val, debt_val)

        st.metric("Health Factor", f"{hf:.4f}")
        st.metric("Distance to Liquidation", f"{drop*100:.2f}% price drop")
        st.metric("Close Factor (if liquidated)", f"{close*100:.0f}%")
        st.metric(
            "Max Borrowable",
            f"{liq_model.max_borrowable(collateral_val):,.1f} ETH",
        )

    st.divider()

    # Exchange rate sensitivity (Lido slashing risk)
    st.subheader("Exchange Rate Sensitivity")
    st.caption(
        "Aave V3 prices wstETH using the Lido protocol exchange rate "
        "(stEthPerToken), not the secondary-market stETH/ETH price. "
        "Only a Lido slashing event can reduce this rate and lower HF."
    )

    peg_at_liq = liq_model.depeg_to_liquidation(
        collateral_amount=position.collateral_amount,
        collateral_price=wsteth_exchange_rate,
        debt_value=debt_val,
    )

    if peg_at_liq > 0:
        rate_drop_pct = (1.0 - peg_at_liq) * 100
        st.info(
            f"Liquidation occurs at exchange rate factor **{peg_at_liq:.4f}** "
            f"(a **{rate_drop_pct:.2f}%** reduction from current rate)"
        )
    else:
        st.error("Position is already at or below liquidation threshold!")

    df_depeg = liq_model.depeg_sensitivity(
        collateral_amount=position.collateral_amount,
        collateral_price=wsteth_exchange_rate,
        debt_value=debt_val,
    )

    fig_depeg = depeg_sensitivity_chart(df_depeg)

    # Add liquidation peg marker
    if peg_at_liq > 0:
        fig_depeg.add_vline(
            x=peg_at_liq,
            line_dash="dot",
            line_color="#f59e0b",
            annotation_text=f"Liq @ {peg_at_liq:.3f}",
        )

    st.plotly_chart(fig_depeg, use_container_width=True)

    # Distance-to-liquidation table
    st.divider()
    st.subheader("Exchange Rate Scenarios")

    scenarios = [1.0, 0.99, 0.98, 0.97, 0.96, 0.95, 0.93, 0.90, 0.85]
    rows = []
    for peg in scenarios:
        adj_collateral = position.collateral_amount * wsteth_exchange_rate * peg
        scenario_hf = liq_model.health_factor(adj_collateral, debt_val)
        status = "Safe" if scenario_hf > 1.0 else "LIQUIDATABLE"
        rows.append(
            {
                "Rate Factor": f"{peg:.2f}",
                "Collateral Value (ETH)": f"{adj_collateral:,.0f}",
                "Health Factor": f"{scenario_hf:.4f}",
                "Status": status,
            }
        )

    st.table(pd.DataFrame(rows))
