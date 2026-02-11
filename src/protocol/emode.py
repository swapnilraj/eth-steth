"""E-mode category dataclass."""

from dataclasses import dataclass


@dataclass(frozen=True)
class EModeCategory:
    """Aave V3 Efficiency Mode category parameters."""

    category_id: int
    label: str
    ltv: float  # e.g. 0.935
    liquidation_threshold: float  # e.g. 0.955
    liquidation_bonus: float  # e.g. 0.01 (1%)
