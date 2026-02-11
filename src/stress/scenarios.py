"""Stress scenario definitions — historical and custom."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StressScenario:
    """A stress scenario with correlated market shocks.

    Attributes:
        name: Short identifier.
        description: Human-readable explanation.
        eth_price_change: Fractional ETH price change (e.g. -0.40 = -40%).
        steth_peg: stETH/ETH peg ratio under stress (e.g. 0.93).
        utilization_shock: Absolute utilization level under stress (e.g. 0.95).
        duration_days: Duration of the stress period.
    """

    name: str
    description: str
    eth_price_change: float
    steth_peg: float
    utilization_shock: float
    duration_days: int


# --- Historical scenarios ---

JUNE_2022_DEPEG = StressScenario(
    name="June 2022 stETH Depeg",
    description="stETH depegged to ~0.93 amid Celsius/3AC collapse. "
    "ETH dropped ~40%, WETH utilization spiked as borrowers fled.",
    eth_price_change=-0.40,
    steth_peg=0.93,
    utilization_shock=0.95,
    duration_days=14,
)

MARCH_2020_BLACK_THURSDAY = StressScenario(
    name="March 2020 Black Thursday",
    description="COVID crash: ETH fell ~50% in 24 hours. "
    "Massive liquidation cascade across DeFi. Gas prices spiked.",
    eth_price_change=-0.50,
    steth_peg=0.98,
    utilization_shock=0.98,
    duration_days=3,
)

MAY_2022_TERRA_LUNA = StressScenario(
    name="May 2022 Terra/Luna",
    description="UST depeg and Luna collapse. ETH dropped ~35%, "
    "stETH depegged to ~0.95 on contagion fears.",
    eth_price_change=-0.35,
    steth_peg=0.95,
    utilization_shock=0.93,
    duration_days=7,
)

HISTORICAL_SCENARIOS = [JUNE_2022_DEPEG, MARCH_2020_BLACK_THURSDAY, MAY_2022_TERRA_LUNA]


def create_custom_scenario(
    name: str,
    eth_price_change: float,
    steth_peg: float,
    utilization_shock: float,
    duration_days: int = 7,
    description: str = "Custom scenario",
) -> StressScenario:
    """Factory for user-defined stress scenarios."""
    return StressScenario(
        name=name,
        description=description,
        eth_price_change=eth_price_change,
        steth_peg=steth_peg,
        utilization_shock=utilization_shock,
        duration_days=duration_days,
    )
