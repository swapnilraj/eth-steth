"""Abstract data provider interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from src.protocol.emode import EModeCategory


@dataclass(frozen=True)
class ReserveParams:
    """Interest rate strategy parameters for a reserve."""

    optimal_utilization: float
    base_rate: float
    slope1: float
    slope2: float
    reserve_factor: float


@dataclass(frozen=True)
class ReserveState:
    """Current state of a reserve pool."""

    total_supply: float  # Total aToken supply (in asset units)
    total_debt: float  # Total variable debt (in asset units)


@dataclass(frozen=True)
class LiquidationParams:
    """Liquidation parameters for an asset."""

    ltv: float  # Loan-to-value ratio (standard)
    liquidation_threshold: float  # Standard liquidation threshold
    liquidation_bonus: float  # Liquidation bonus (e.g. 0.05 = 5%)


class PoolDataProvider(ABC):
    """Abstract interface for Aave pool data."""

    @abstractmethod
    def get_reserve_params(self, asset: str) -> ReserveParams:
        """Get interest rate parameters for a reserve."""

    @abstractmethod
    def get_reserve_state(self, asset: str) -> ReserveState:
        """Get current pool state for a reserve."""

    @abstractmethod
    def get_liquidation_params(self, asset: str) -> LiquidationParams:
        """Get liquidation parameters for an asset."""

    @abstractmethod
    def get_emode_category(self, category_id: int) -> EModeCategory:
        """Get E-mode category parameters."""

    @abstractmethod
    def get_asset_price(self, asset: str) -> float:
        """Get asset price in ETH terms."""

    @abstractmethod
    def get_steth_eth_peg(self) -> float:
        """Get stETH/ETH market exchange rate from Chainlink.

        Note: Aave V3 uses a hardcoded 1:1 stETH/ETH in its oracle, so
        this market rate does NOT affect on-chain health factors.  In the
        dashboard it is used as the baseline for exchange-rate shock
        scenarios (modelling Lido slashing events).
        """

    @abstractmethod
    def get_staking_apy(self) -> float:
        """Get current Lido stETH staking APY as a decimal (e.g. 0.035 = 3.5%)."""
