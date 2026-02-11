"""Simulations page — Monte Carlo, liquidation cascade, and unwind cost."""

import pandas as pd
import streamlit as st

from src.dashboard.components.charts import (
    cascade_waterfall_chart,
    liquidation_probability_chart,
    pnl_distribution_histogram,
    rate_fan_chart,
    unwind_cost_breakdown_chart,
)
from src.data.constants import WETH, WSTETH
from src.data.interfaces import PoolDataProvider
from src.position.unwind import (
    DEXPoolParams,
    estimate_unwind_cost_detailed,
)
from src.position.vault_position import VaultPosition
from src.protocol.interest_rate import InterestRateModel, InterestRateParams
from src.protocol.pool import PoolState
from src.simulation.liquidation_cascade import CascadeConfig, simulate_cascade
from src.simulation.monte_carlo import OUParams, run_monte_carlo


def render_simulations(
    position: VaultPosition,
    provider: PoolDataProvider,
    staking_apy: float,
) -> None:
    """Render the simulations page with 3 sections."""
    st.header("Simulations")

    collateral_val = position.collateral_value(provider)
    debt_val = position.debt_value(provider)
    liq_model = position.get_liquidation_model(provider)

    # Get current pool state for utilization
    weth_state = PoolState.from_reserve_state(provider.get_reserve_state(WETH))
    weth_params = provider.get_reserve_params(WETH)
    u0 = weth_state.utilization

    # wstETH supply APY for MC income
    wsteth_params = provider.get_reserve_params(WSTETH)
    wsteth_state = PoolState.from_reserve_state(provider.get_reserve_state(WSTETH))
    wsteth_rate_model = InterestRateModel(wsteth_params)
    wsteth_supply_apy = wsteth_rate_model.supply_rate(
        wsteth_state.total_debt / wsteth_state.total_supply if wsteth_state.total_supply > 0 else 0.0
    )

    # --- Section 1: Monte Carlo ---
    st.subheader("Monte Carlo Simulation")

    with st.expander("Simulation Parameters", expanded=False):
        mc_col1, mc_col2, mc_col3 = st.columns(3)
        with mc_col1:
            n_paths = st.number_input("Paths", min_value=100, max_value=10000, value=1000, step=100)
            horizon = st.number_input("Horizon (days)", min_value=30, max_value=730, value=365, step=30)
        with mc_col2:
            ou_theta = st.number_input("Mean Utilization", min_value=0.1, max_value=0.99, value=u0, step=0.01, format="%.2f")
            ou_kappa = st.number_input("Mean Reversion Speed", min_value=0.5, max_value=20.0, value=5.0, step=0.5)
        with mc_col3:
            ou_sigma = st.number_input("Utilization Volatility", min_value=0.01, max_value=0.30, value=0.08, step=0.01, format="%.2f")
            mc_seed = st.number_input("Random Seed", min_value=0, max_value=99999, value=42, step=1)

    ou_params = OUParams(theta=ou_theta, kappa=ou_kappa, sigma=ou_sigma)

    mc_result = run_monte_carlo(
        u0=u0,
        collateral_value=collateral_val,
        debt_value=debt_val,
        liquidation_threshold=liq_model.liquidation_threshold,
        staking_apy=staking_apy,
        supply_apy=wsteth_supply_apy,
        optimal_utilization=weth_params.optimal_utilization,
        base_rate=weth_params.base_rate,
        slope1=weth_params.slope1,
        slope2=weth_params.slope2,
        ou_params=ou_params,
        n_paths=int(n_paths),
        horizon_days=int(horizon),
        seed=int(mc_seed),
    )

    # KPIs
    import numpy as np

    median_pnl = float(np.median(mc_result.terminal_pnl))
    mean_rate = float(np.mean(mc_result.rate_paths[:, -1]) * 100)
    liq_prob = float(np.mean(mc_result.liquidated) * 100)
    p5_pnl = float(np.percentile(mc_result.terminal_pnl, 5))

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("Median P&L", f"{median_pnl:,.0f} ETH")
    with kpi2:
        st.metric("Mean Final Rate", f"{mean_rate:.2f}%")
    with kpi3:
        st.metric("Liquidation Prob", f"{liq_prob:.1f}%")
    with kpi4:
        st.metric("5th Percentile P&L", f"{p5_pnl:,.0f} ETH")

    # Charts
    chart_col1, chart_col2 = st.columns(2)
    with chart_col1:
        fig_fan = rate_fan_chart(mc_result)
        st.plotly_chart(fig_fan, use_container_width=True)
    with chart_col2:
        fig_hist = pnl_distribution_histogram(mc_result)
        st.plotly_chart(fig_hist, use_container_width=True)

    fig_liq = liquidation_probability_chart(mc_result)
    st.plotly_chart(fig_liq, use_container_width=True)

    st.divider()

    # --- Section 2: Liquidation Cascade ---
    st.subheader("Liquidation Cascade Analysis")

    cas_col1, cas_col2, cas_col3 = st.columns(3)
    with cas_col1:
        init_debt = st.number_input(
            "Initial Debt to Liquidate",
            min_value=1000.0,
            max_value=1_000_000.0,
            value=100_000.0,
            step=10_000.0,
            format="%.0f",
        )
    with cas_col2:
        liq_bonus = st.number_input(
            "Liquidation Bonus",
            min_value=0.001,
            max_value=0.10,
            value=0.01,
            step=0.005,
            format="%.3f",
        )
    with cas_col3:
        rate_sens = st.number_input(
            "Rate Sensitivity",
            min_value=0.0,
            max_value=0.20,
            value=0.05,
            step=0.01,
            format="%.2f",
        )

    wsteth_price = provider.get_asset_price(WSTETH)
    cascade_config = CascadeConfig(
        initial_debt_to_liquidate=init_debt,
        collateral_price=wsteth_price,
        liquidation_bonus=liq_bonus,
        rate_sensitivity=rate_sens,
    )

    rate_params = InterestRateParams(
        optimal_utilization=weth_params.optimal_utilization,
        base_rate=weth_params.base_rate,
        slope1=weth_params.slope1,
        slope2=weth_params.slope2,
        reserve_factor=weth_params.reserve_factor,
    )

    cascade_result = simulate_cascade(weth_state, rate_params, cascade_config)

    cas_kpi1, cas_kpi2, cas_kpi3 = st.columns(3)
    with cas_kpi1:
        st.metric("Total Debt Liquidated", f"{cascade_result.total_debt_liquidated:,.0f}")
    with cas_kpi2:
        st.metric("Total Collateral Seized", f"{cascade_result.total_collateral_seized:,.0f}")
    with cas_kpi3:
        st.metric("Final Utilization", f"{cascade_result.final_utilization*100:.1f}%")

    fig_cascade = cascade_waterfall_chart(cascade_result)
    st.plotly_chart(fig_cascade, use_container_width=True)

    # Step table
    if cascade_result.steps:
        rows = []
        for s in cascade_result.steps:
            rows.append({
                "Step": s.step,
                "Debt Liquidated": f"{s.debt_liquidated:,.0f}",
                "Collateral Seized": f"{s.collateral_seized:,.0f}",
                "Utilization": f"{s.utilization*100:.1f}%",
                "Borrow Rate": f"{s.borrow_rate*100:.2f}%",
                "At-Risk Debt": f"{s.at_risk_debt:,.0f}",
            })
        st.table(pd.DataFrame(rows))

    st.divider()

    # --- Section 3: Unwind Cost ---
    st.subheader("Unwind Cost Estimation")

    uw_col1, uw_col2, uw_col3 = st.columns(3)
    with uw_col1:
        pool_reserve_x = st.number_input(
            "Pool wstETH Reserve",
            min_value=1000.0,
            max_value=500_000.0,
            value=50_000.0,
            step=5_000.0,
            format="%.0f",
        )
    with uw_col2:
        pool_reserve_y = st.number_input(
            "Pool WETH Reserve",
            min_value=1000.0,
            max_value=500_000.0,
            value=59_000.0,
            step=5_000.0,
            format="%.0f",
        )
    with uw_col3:
        pool_fee = st.number_input(
            "Pool Fee (bps)",
            min_value=1.0,
            max_value=100.0,
            value=30.0,
            step=1.0,
        )

    pool = DEXPoolParams(
        reserve_x=pool_reserve_x,
        reserve_y=pool_reserve_y,
        fee_bps=pool_fee,
    )

    unwind_result = estimate_unwind_cost_detailed(
        debt_amount=position.debt_amount,
        pool=pool,
    )

    uw_kpi1, uw_kpi2, uw_kpi3 = st.columns(3)
    with uw_kpi1:
        st.metric("Total Unwind Cost", f"{unwind_result.total_cost:.2f} ETH")
    with uw_kpi2:
        st.metric("Price Impact", f"{unwind_result.price_impact*100:.2f}%")
    with uw_kpi3:
        st.metric("Effective Slippage", f"{unwind_result.effective_slippage_bps:.1f} bps")

    fig_unwind = unwind_cost_breakdown_chart(
        unwind_result.slippage_cost,
        unwind_result.gas_cost,
        unwind_result.total_cost,
    )
    st.plotly_chart(fig_unwind, use_container_width=True)

    # Size sensitivity curve
    st.caption("Unwind Cost vs Trade Size")
    sizes = [1_000, 2_500, 5_000, 10_000, 15_000, 20_000, 30_000, 50_000]
    size_rows = []
    for size in sizes:
        r = estimate_unwind_cost_detailed(debt_amount=float(size), pool=pool)
        size_rows.append({
            "Debt Size": f"{size:,}",
            "Slippage Cost": f"{r.slippage_cost:.2f} ETH",
            "Impact": f"{r.price_impact*100:.3f}%",
            "Total Cost": f"{r.total_cost:.2f} ETH",
        })
    st.table(pd.DataFrame(size_rows))
