"""Reusable metric card components for the dashboard."""

import streamlit as st


def metric_card(label: str, value: str, delta: str | None = None) -> None:
    """Display a single metric using Streamlit's built-in metric."""
    st.metric(label=label, value=value, delta=delta)


def kpi_row(metrics: list[tuple[str, str, str | None]]) -> None:
    """Display a row of KPI cards.

    Args:
        metrics: List of (label, value, delta) tuples.
    """
    cols = st.columns(len(metrics))
    for col, (label, value, delta) in zip(cols, metrics):
        with col:
            metric_card(label, value, delta)
