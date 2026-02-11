"""Reusable Plotly chart components."""

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from src.simulation.results import CascadeResult, MonteCarloResult
from src.stress.var import VaRResult


def rate_curve_chart(
    df: pd.DataFrame,
    current_utilization: float | None = None,
    title: str = "Interest Rate Curve",
) -> go.Figure:
    """Create an interactive rate curve chart.

    Args:
        df: DataFrame with columns: utilization, borrow_rate, supply_rate.
        current_utilization: If provided, marks current utilization on chart.
        title: Chart title.
    """
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["utilization"] * 100,
            y=df["borrow_rate"] * 100,
            name="Borrow Rate",
            line=dict(color="#ef4444", width=2),
            hovertemplate="Utilization: %{x:.1f}%<br>Borrow Rate: %{y:.2f}%<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=df["utilization"] * 100,
            y=df["supply_rate"] * 100,
            name="Supply Rate",
            line=dict(color="#22c55e", width=2),
            hovertemplate="Utilization: %{x:.1f}%<br>Supply Rate: %{y:.2f}%<extra></extra>",
        )
    )

    if current_utilization is not None:
        fig.add_vline(
            x=current_utilization * 100,
            line_dash="dash",
            line_color="#6b7280",
            annotation_text=f"Current: {current_utilization*100:.1f}%",
        )

    fig.update_layout(
        title=title,
        xaxis_title="Utilization (%)",
        yaxis_title="Rate (%)",
        hovermode="x unified",
        template="plotly_dark",
        height=450,
    )

    return fig


def health_factor_gauge(hf: float) -> go.Figure:
    """Create a health factor gauge chart."""
    # Clamp display value
    display_hf = min(hf, 3.0) if hf != float("inf") else 3.0

    if hf >= 1.5:
        color = "#22c55e"  # green
    elif hf >= 1.1:
        color = "#f59e0b"  # amber
    else:
        color = "#ef4444"  # red

    fig = go.Figure(
        go.Indicator(
            mode="gauge+number",
            value=display_hf,
            number={"suffix": "", "font": {"size": 40}, "valueformat": ".2f"},
            title={"text": "Health Factor", "font": {"size": 16}},
            domain={"x": [0, 1], "y": [0.15, 1]},
            gauge={
                "axis": {"range": [0, 3], "tickwidth": 1},
                "bar": {"color": color},
                "steps": [
                    {"range": [0, 1], "color": "rgba(239,68,68,0.2)"},
                    {"range": [1, 1.5], "color": "rgba(245,158,11,0.2)"},
                    {"range": [1.5, 3], "color": "rgba(34,197,94,0.2)"},
                ],
                "threshold": {
                    "line": {"color": "white", "width": 2},
                    "thickness": 0.75,
                    "value": 1.0,
                },
            },
        )
    )

    fig.update_layout(
        template="plotly_dark",
        height=350,
        margin=dict(t=40, b=0, l=30, r=30),
    )

    return fig


def depeg_sensitivity_chart(df: pd.DataFrame) -> go.Figure:
    """Create a depeg sensitivity chart showing HF vs peg ratio.

    Args:
        df: DataFrame with columns: peg_ratio, health_factor.
    """
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=df["peg_ratio"],
            y=df["health_factor"],
            mode="lines",
            name="Health Factor",
            line=dict(color="#3b82f6", width=2),
            hovertemplate="Peg: %{x:.3f}<br>HF: %{y:.3f}<extra></extra>",
        )
    )

    # Liquidation line at HF = 1.0
    fig.add_hline(
        y=1.0,
        line_dash="dash",
        line_color="#ef4444",
        annotation_text="Liquidation (HF=1.0)",
    )

    fig.update_layout(
        title="Health Factor vs stETH/ETH Peg",
        xaxis_title="stETH/ETH Peg Ratio",
        yaxis_title="Health Factor",
        template="plotly_dark",
        height=450,
    )

    return fig


# --- Phase 2/3 charts ---


def rate_fan_chart(mc_result: MonteCarloResult) -> go.Figure:
    """Percentile fan chart of borrow rates over time."""
    days = mc_result.timesteps
    rates = mc_result.rate_paths * 100  # to percent

    p5 = np.percentile(rates, 5, axis=0)
    p25 = np.percentile(rates, 25, axis=0)
    p50 = np.percentile(rates, 50, axis=0)
    p75 = np.percentile(rates, 75, axis=0)
    p95 = np.percentile(rates, 95, axis=0)

    fig = go.Figure()

    # 5-95 band
    fig.add_trace(
        go.Scatter(
            x=np.concatenate([days, days[::-1]]),
            y=np.concatenate([p95, p5[::-1]]),
            fill="toself",
            fillcolor="rgba(59,130,246,0.1)",
            line=dict(color="rgba(0,0,0,0)"),
            name="5th-95th percentile",
            hoverinfo="skip",
        )
    )

    # 25-75 band
    fig.add_trace(
        go.Scatter(
            x=np.concatenate([days, days[::-1]]),
            y=np.concatenate([p75, p25[::-1]]),
            fill="toself",
            fillcolor="rgba(59,130,246,0.25)",
            line=dict(color="rgba(0,0,0,0)"),
            name="25th-75th percentile",
            hoverinfo="skip",
        )
    )

    # Median
    fig.add_trace(
        go.Scatter(
            x=days,
            y=p50,
            mode="lines",
            name="Median",
            line=dict(color="#3b82f6", width=2),
            hovertemplate="Day %{x:.0f}<br>Rate: %{y:.2f}%<extra></extra>",
        )
    )

    fig.update_layout(
        title="Borrow Rate Fan Chart",
        xaxis_title="Day",
        yaxis_title="Borrow Rate (%)",
        template="plotly_dark",
        height=450,
    )

    return fig


def pnl_distribution_histogram(mc_result: MonteCarloResult) -> go.Figure:
    """Histogram of terminal P&L with key statistics."""
    pnl = mc_result.terminal_pnl

    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=pnl,
            nbinsx=50,
            marker_color="#3b82f6",
            opacity=0.75,
            name="P&L Distribution",
            hovertemplate="P&L: %{x:.1f} ETH<br>Count: %{y}<extra></extra>",
        )
    )

    median = float(np.median(pnl))
    p5 = float(np.percentile(pnl, 5))
    p95 = float(np.percentile(pnl, 95))

    fig.add_vline(x=median, line_dash="solid", line_color="#22c55e",
                  annotation_text=f"Median: {median:.0f}")
    fig.add_vline(x=p5, line_dash="dash", line_color="#ef4444",
                  annotation_text=f"5th: {p5:.0f}")
    fig.add_vline(x=p95, line_dash="dash", line_color="#22c55e",
                  annotation_text=f"95th: {p95:.0f}")

    fig.update_layout(
        title="Terminal P&L Distribution",
        xaxis_title="P&L (ETH)",
        yaxis_title="Count",
        template="plotly_dark",
        height=450,
    )

    return fig


def liquidation_probability_chart(mc_result: MonteCarloResult) -> go.Figure:
    """Cumulative liquidation fraction over time."""
    n_paths = mc_result.pnl_paths.shape[0]
    n_steps = mc_result.pnl_paths.shape[1]
    days = mc_result.timesteps

    # For each time step, compute fraction of paths that have been liquidated by then
    # Use the same threshold as in monte_carlo.py
    equity = mc_result.pnl_paths[:, 0]  # Not exactly right, but we use liquidated flag
    # Simpler: use cumulative min P&L to detect "ever liquidated by time t"
    cum_min_pnl = np.minimum.accumulate(mc_result.pnl_paths, axis=1)

    # If any path's P&L ever drops below the terminal check, count it
    # For simplicity, use fraction of liquidated paths that triggered by each step
    # We'll approximate by checking each step
    liq_fraction = np.zeros(n_steps)
    if np.any(mc_result.liquidated):
        # Find first liquidation time per path
        for t in range(n_steps):
            # Paths liquidated by step t: cumulative
            liq_by_t = np.sum(mc_result.liquidated & (cum_min_pnl[:, t] <= cum_min_pnl[:, -1]))
            liq_fraction[t] = liq_by_t / n_paths
        # Ensure monotonically non-decreasing
        liq_fraction = np.maximum.accumulate(liq_fraction)
    else:
        liq_fraction = np.zeros(n_steps)

    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=days,
            y=liq_fraction * 100,
            mode="lines",
            fill="tozeroy",
            fillcolor="rgba(239,68,68,0.15)",
            line=dict(color="#ef4444", width=2),
            name="Liquidation Probability",
            hovertemplate="Day %{x:.0f}<br>Prob: %{y:.2f}%<extra></extra>",
        )
    )

    fig.update_layout(
        title="Cumulative Liquidation Probability",
        xaxis_title="Day",
        yaxis_title="Liquidation Probability (%)",
        template="plotly_dark",
        height=400,
        yaxis=dict(range=[0, max(100, float(np.max(liq_fraction) * 100) + 5)]),
    )

    return fig


def cascade_waterfall_chart(cascade_result: CascadeResult) -> go.Figure:
    """Dual-axis chart: debt liquidated bars + borrow rate line per cascade step."""
    if not cascade_result.steps:
        fig = go.Figure()
        fig.update_layout(title="No cascade steps", template="plotly_dark", height=400)
        return fig

    steps = [s.step for s in cascade_result.steps]
    debts = [s.debt_liquidated for s in cascade_result.steps]
    rates = [s.borrow_rate * 100 for s in cascade_result.steps]

    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=steps,
            y=debts,
            name="Debt Liquidated",
            marker_color="#ef4444",
            opacity=0.8,
            yaxis="y",
            hovertemplate="Step %{x}<br>Debt: %{y:,.0f}<extra></extra>",
        )
    )

    fig.add_trace(
        go.Scatter(
            x=steps,
            y=rates,
            name="Borrow Rate (%)",
            line=dict(color="#f59e0b", width=2),
            yaxis="y2",
            hovertemplate="Step %{x}<br>Rate: %{y:.2f}%<extra></extra>",
        )
    )

    fig.update_layout(
        title="Liquidation Cascade Waterfall",
        xaxis_title="Cascade Step",
        yaxis=dict(title="Debt Liquidated", side="left"),
        yaxis2=dict(title="Borrow Rate (%)", side="right", overlaying="y"),
        template="plotly_dark",
        height=450,
        legend=dict(x=0.01, y=0.99),
    )

    return fig


def unwind_cost_breakdown_chart(
    slippage_cost: float,
    gas_cost: float,
    total_cost: float,
) -> go.Figure:
    """Stacked bar chart: slippage vs gas cost."""
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=["Unwind Cost"],
            y=[slippage_cost],
            name="Slippage/Impact",
            marker_color="#ef4444",
        )
    )

    fig.add_trace(
        go.Bar(
            x=["Unwind Cost"],
            y=[gas_cost],
            name="Gas Cost",
            marker_color="#f59e0b",
        )
    )

    fig.update_layout(
        title=f"Unwind Cost Breakdown (Total: {total_cost:.2f} ETH)",
        yaxis_title="Cost (ETH)",
        barmode="stack",
        template="plotly_dark",
        height=400,
    )

    return fig


def scenario_comparison_chart(
    scenario_names: list[str],
    hf_before: list[float],
    hf_after: list[float],
) -> go.Figure:
    """Grouped bar chart: HF before/after for each scenario."""
    fig = go.Figure()

    fig.add_trace(
        go.Bar(
            x=scenario_names,
            y=hf_before,
            name="HF Before",
            marker_color="#22c55e",
            opacity=0.8,
        )
    )

    fig.add_trace(
        go.Bar(
            x=scenario_names,
            y=hf_after,
            name="HF After",
            marker_color="#ef4444",
            opacity=0.8,
        )
    )

    fig.add_hline(y=1.0, line_dash="dash", line_color="white",
                  annotation_text="Liquidation (HF=1.0)")

    fig.update_layout(
        title="Stress Scenario: Health Factor Impact",
        yaxis_title="Health Factor",
        barmode="group",
        template="plotly_dark",
        height=450,
    )

    return fig


def var_summary_chart(pnl_array: np.ndarray, var_result: VaRResult) -> go.Figure:
    """P&L histogram with VaR/CVaR vertical lines."""
    fig = go.Figure()

    fig.add_trace(
        go.Histogram(
            x=pnl_array,
            nbinsx=50,
            marker_color="#3b82f6",
            opacity=0.7,
            name="P&L",
        )
    )

    fig.add_vline(x=var_result.var_95, line_dash="dash", line_color="#f59e0b",
                  annotation_text=f"VaR95: {var_result.var_95:.0f}")
    fig.add_vline(x=var_result.var_99, line_dash="dash", line_color="#ef4444",
                  annotation_text=f"VaR99: {var_result.var_99:.0f}")
    fig.add_vline(x=var_result.cvar_95, line_dash="dot", line_color="#f59e0b",
                  annotation_text=f"CVaR95: {var_result.cvar_95:.0f}")

    fig.update_layout(
        title="P&L Distribution with VaR",
        xaxis_title="P&L (ETH)",
        yaxis_title="Count",
        template="plotly_dark",
        height=450,
    )

    return fig


def correlated_scatter_chart(
    peg_values: np.ndarray,
    util_values: np.ndarray,
    pnl_values: np.ndarray,
) -> go.Figure:
    """Scatter: peg vs utilization colored by P&L impact."""
    fig = go.Figure()

    fig.add_trace(
        go.Scatter(
            x=peg_values,
            y=util_values * 100,
            mode="markers",
            marker=dict(
                color=pnl_values,
                colorscale="RdYlGn",
                size=5,
                colorbar=dict(title="P&L (ETH)"),
                opacity=0.6,
            ),
            hovertemplate="Peg: %{x:.3f}<br>Util: %{y:.1f}%<br>P&L: %{marker.color:.0f} ETH<extra></extra>",
        )
    )

    fig.update_layout(
        title="Correlated Shock Scenarios",
        xaxis_title="stETH/ETH Peg",
        yaxis_title="Utilization (%)",
        template="plotly_dark",
        height=450,
    )

    return fig
