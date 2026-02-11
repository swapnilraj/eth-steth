"""Stress Tests page — historical scenarios, custom scenarios, VaR, correlated shocks."""

import numpy as np
import pandas as pd
import streamlit as st

from src.dashboard.components.charts import (
    correlated_scatter_chart,
    scenario_comparison_chart,
    var_summary_chart,
)
from src.data.constants import WETH, WSTETH
from src.data.interfaces import PoolDataProvider
from src.position.vault_position import VaultPosition
from src.protocol.pool import PoolState
from src.protocol.interest_rate import InterestRateModel
from src.simulation.monte_carlo import OUParams, run_monte_carlo
from src.stress.scenarios import HISTORICAL_SCENARIOS, create_custom_scenario
from src.stress.shock_engine import apply_scenario, generate_correlated_scenarios
from src.stress.var import VaRResult, compute_var, compute_var_from_scenarios


def render_stress_tests(
    position: VaultPosition,
    provider: PoolDataProvider,
    staking_apy: float,
) -> None:
    """Render the stress tests page with 4 sections."""
    st.header("Stress Tests")

    collateral_val = position.collateral_value(provider)
    debt_val = position.debt_value(provider)
    # The oracle price includes the peg. Extract exchange-rate-only price
    # for stress/depeg analysis so we don't double-count.
    current_peg = provider.get_steth_eth_peg()
    oracle_price = provider.get_asset_price(WSTETH)
    collateral_price = oracle_price / current_peg if current_peg > 0 else oracle_price
    liq_model = position.get_liquidation_model(provider)

    # --- Section 1: Historical Scenarios ---
    st.subheader("Historical Stress Scenarios")

    results = []
    names = []
    hf_befores = []
    hf_afters = []

    for scenario in HISTORICAL_SCENARIOS:
        shock = apply_scenario(
            scenario=scenario,
            collateral_amount=position.collateral_amount,
            collateral_price=collateral_price,
            debt_value=debt_val,
            liquidation_threshold=liq_model.liquidation_threshold,
            current_peg=current_peg,
        )
        results.append(shock)
        names.append(scenario.name)
        hf_befores.append(shock.hf_before)
        hf_afters.append(shock.hf_after)

    # Scenario table
    rows = []
    for scenario, shock in zip(HISTORICAL_SCENARIOS, results):
        rows.append({
            "Scenario": scenario.name,
            "ETH Change": f"{scenario.eth_price_change*100:+.0f}%",
            "stETH Peg": f"{scenario.steth_peg:.2f}",
            "Utilization": f"{scenario.utilization_shock*100:.0f}%",
            "HF Before": f"{shock.hf_before:.3f}",
            "HF After": f"{shock.hf_after:.3f}",
            "P&L Impact": f"{shock.pnl_impact:,.0f} ETH",
            "Liquidated": "Yes" if shock.is_liquidated else "No",
        })
    st.table(pd.DataFrame(rows))

    fig_comp = scenario_comparison_chart(names, hf_befores, hf_afters)
    st.plotly_chart(fig_comp, use_container_width=True)

    st.divider()

    # --- Section 2: Custom Scenario Builder ---
    st.subheader("Custom Scenario Builder")

    cs_col1, cs_col2, cs_col3, cs_col4 = st.columns(4)
    with cs_col1:
        custom_eth = st.slider(
            "ETH Price Change (%)",
            min_value=-80,
            max_value=50,
            value=-30,
            step=5,
        ) / 100.0
    with cs_col2:
        custom_peg = st.slider(
            "stETH/ETH Peg",
            min_value=0.80,
            max_value=1.00,
            value=0.95,
            step=0.01,
            format="%.2f",
        )
    with cs_col3:
        custom_util = st.slider(
            "Utilization Shock (%)",
            min_value=50,
            max_value=100,
            value=95,
            step=1,
        ) / 100.0
    with cs_col4:
        custom_days = st.number_input(
            "Duration (days)",
            min_value=1,
            max_value=90,
            value=7,
            step=1,
        )

    custom_scenario = create_custom_scenario(
        name="Custom",
        eth_price_change=custom_eth,
        steth_peg=custom_peg,
        utilization_shock=custom_util,
        duration_days=int(custom_days),
    )

    custom_result = apply_scenario(
        scenario=custom_scenario,
        collateral_amount=position.collateral_amount,
        collateral_price=collateral_price,
        debt_value=debt_val,
        liquidation_threshold=liq_model.liquidation_threshold,
        current_peg=current_peg,
    )

    cr_col1, cr_col2, cr_col3, cr_col4 = st.columns(4)
    with cr_col1:
        st.metric("HF Before", f"{custom_result.hf_before:.3f}")
    with cr_col2:
        delta_hf = custom_result.hf_after - custom_result.hf_before
        st.metric("HF After", f"{custom_result.hf_after:.3f}", f"{delta_hf:+.3f}")
    with cr_col3:
        st.metric("P&L Impact", f"{custom_result.pnl_impact:,.0f} ETH")
    with cr_col4:
        if custom_result.is_liquidated:
            st.error("LIQUIDATED")
        else:
            st.success("Safe")

    st.divider()

    # --- Section 3: VaR / Tail Risk from Monte Carlo ---
    st.subheader("Value at Risk (Monte Carlo)")

    weth_state = PoolState.from_reserve_state(provider.get_reserve_state(WETH))
    weth_params = provider.get_reserve_params(WETH)

    # wstETH supply APY for MC income
    wsteth_params = provider.get_reserve_params(WSTETH)
    wsteth_state = PoolState.from_reserve_state(provider.get_reserve_state(WSTETH))
    wsteth_rate_model = InterestRateModel(wsteth_params)
    wsteth_supply_apy = wsteth_rate_model.supply_rate(
        wsteth_state.total_debt / wsteth_state.total_supply if wsteth_state.total_supply > 0 else 0.0
    )

    mc_result = run_monte_carlo(
        u0=weth_state.utilization,
        collateral_value=collateral_val,
        debt_value=debt_val,
        liquidation_threshold=liq_model.liquidation_threshold,
        staking_apy=staking_apy,
        supply_apy=wsteth_supply_apy,
        optimal_utilization=weth_params.optimal_utilization,
        base_rate=weth_params.base_rate,
        slope1=weth_params.slope1,
        slope2=weth_params.slope2,
        n_paths=2000,
        horizon_days=365,
        seed=42,
    )

    var_result = compute_var(mc_result)

    var_col1, var_col2, var_col3, var_col4 = st.columns(4)
    with var_col1:
        st.metric("VaR (95%)", f"{var_result.var_95:,.0f} ETH")
    with var_col2:
        st.metric("VaR (99%)", f"{var_result.var_99:,.0f} ETH")
    with var_col3:
        st.metric("CVaR (95%)", f"{var_result.cvar_95:,.0f} ETH")
    with var_col4:
        st.metric("Max Loss", f"{var_result.max_loss:,.0f} ETH")

    fig_var = var_summary_chart(mc_result.terminal_pnl, var_result)
    st.plotly_chart(fig_var, use_container_width=True)

    st.divider()

    # --- Section 4: Correlated Shock Analysis ---
    st.subheader("Correlated Shock Analysis")

    n_corr = st.number_input(
        "Number of Correlated Scenarios",
        min_value=100,
        max_value=10000,
        value=1000,
        step=100,
    )

    corr_scenarios = generate_correlated_scenarios(
        n_scenarios=int(n_corr),
        seed=42,
    )

    # Apply each correlated scenario.
    # For an ETH-denominated position, ETH/USD moves cancel out (both
    # collateral and debt are in ETH). The risk factors that matter are:
    #   1) stETH/ETH peg deviation (affects collateral value)
    #   2) utilization shock (affects borrow rate → cost)
    weth_rate_model = InterestRateModel(weth_params)
    corr_pnl = np.empty(len(corr_scenarios))
    horizon_days = 30  # assume 30-day stress horizon
    for i, shock_vec in enumerate(corr_scenarios):
        _eth_change, peg, util = shock_vec
        # Collateral impact: only peg matters (ETH price change is irrelevant)
        stressed_collateral = position.collateral_amount * collateral_price * peg
        collateral_pnl = stressed_collateral - collateral_val
        # Borrow cost impact from utilization shock
        stressed_rate = weth_rate_model.variable_borrow_rate(util)
        borrow_cost = debt_val * stressed_rate * (horizon_days / 365.0)
        staking_income = collateral_val * staking_apy * (horizon_days / 365.0)
        corr_pnl[i] = collateral_pnl + staking_income - borrow_cost

    corr_var = compute_var_from_scenarios(
        corr_pnl,
        collateral_value=collateral_val,
        debt_value=debt_val,
        liquidation_threshold=liq_model.liquidation_threshold,
    )

    cv_col1, cv_col2, cv_col3 = st.columns(3)
    with cv_col1:
        st.metric("Correlated VaR (95%)", f"{corr_var.var_95:,.0f} ETH")
    with cv_col2:
        st.metric("Correlated VaR (99%)", f"{corr_var.var_99:,.0f} ETH")
    with cv_col3:
        st.metric("Correlated CVaR (95%)", f"{corr_var.cvar_95:,.0f} ETH")

    fig_scatter = correlated_scatter_chart(
        peg_values=corr_scenarios[:, 1],
        util_values=corr_scenarios[:, 2],
        pnl_values=corr_pnl,
    )
    st.plotly_chart(fig_scatter, use_container_width=True)
