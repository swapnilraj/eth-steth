"""Interest Rates page — interactive rate curves and sensitivity."""

import pandas as pd
import streamlit as st

from src.dashboard.components.charts import rate_curve_chart
from src.data.constants import WETH, WSTETH
from src.data.interfaces import PoolDataProvider
from src.protocol.interest_rate import InterestRateModel
from src.protocol.pool import PoolModel, PoolState


def render_rates(
    provider: PoolDataProvider,
    utilization_override: float | None = None,
) -> None:
    """Render the interest rates page."""
    st.header("Interest Rate Curves")

    # Build models for both assets
    weth_params = provider.get_reserve_params(WETH)
    wsteth_params = provider.get_reserve_params(WSTETH)
    weth_rate_model = InterestRateModel(weth_params)
    wsteth_rate_model = InterestRateModel(wsteth_params)

    # Current pool states
    weth_state = PoolState.from_reserve_state(provider.get_reserve_state(WETH))
    wsteth_state = PoolState.from_reserve_state(provider.get_reserve_state(WSTETH))

    weth_util = utilization_override if utilization_override is not None else weth_state.utilization
    wsteth_util = wsteth_state.utilization

    # WETH rate curve
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("WETH")
        df_weth = weth_rate_model.rate_curve()
        fig_weth = rate_curve_chart(df_weth, current_utilization=weth_util, title="WETH Rate Curve")
        st.plotly_chart(fig_weth, use_container_width=True)

        st.metric("Current Utilization", f"{weth_util*100:.1f}%")
        st.metric("Borrow Rate", f"{weth_rate_model.variable_borrow_rate(weth_util)*100:.2f}%")
        st.metric("Supply Rate", f"{weth_rate_model.supply_rate(weth_util)*100:.2f}%")

    with col2:
        st.subheader("wstETH")
        df_wsteth = wsteth_rate_model.rate_curve()
        fig_wsteth = rate_curve_chart(df_wsteth, current_utilization=wsteth_util, title="wstETH Rate Curve")
        st.plotly_chart(fig_wsteth, use_container_width=True)

        st.metric("Current Utilization", f"{wsteth_util*100:.1f}%")
        st.metric("Borrow Rate", f"{wsteth_rate_model.variable_borrow_rate(wsteth_util)*100:.2f}%")
        st.metric("Supply Rate", f"{wsteth_rate_model.supply_rate(wsteth_util)*100:.4f}%")

    # Rate sensitivity table
    st.divider()
    st.subheader("WETH Rate Sensitivity")

    utilizations = [0.2, 0.4, 0.6, 0.8, 0.90, 0.92, 0.95, 0.98, 1.0]
    rows = []
    for u in utilizations:
        rows.append(
            {
                "Utilization": f"{u*100:.0f}%",
                "Borrow Rate": f"{weth_rate_model.variable_borrow_rate(u)*100:.2f}%",
                "Supply Rate": f"{weth_rate_model.supply_rate(u)*100:.2f}%",
            }
        )
    st.table(pd.DataFrame(rows))

    # Borrow impact simulation
    st.divider()
    st.subheader("Borrow Impact Simulation")

    weth_pool_model = PoolModel(weth_state, weth_rate_model)
    borrow_amount = st.slider(
        "Additional WETH Borrow",
        min_value=0,
        max_value=500_000,
        value=100_000,
        step=10_000,
    )

    if borrow_amount > 0:
        impact = weth_pool_model.simulate_borrow(float(borrow_amount))
        c1, c2 = st.columns(2)
        with c1:
            st.metric(
                "Utilization",
                f"{impact['utilization_after']*100:.1f}%",
                f"{(impact['utilization_after']-impact['utilization_before'])*100:+.1f}%",
            )
        with c2:
            st.metric(
                "Borrow Rate",
                f"{impact['borrow_rate_after']*100:.2f}%",
                f"{(impact['borrow_rate_after']-impact['borrow_rate_before'])*100:+.2f}%",
            )
