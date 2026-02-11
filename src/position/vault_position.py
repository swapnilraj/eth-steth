"""Mellow vault position state."""

from dataclasses import dataclass

from src.data.constants import EMODE_ETH_CORRELATED, WETH, WSTETH
from src.data.interfaces import PoolDataProvider
from src.protocol.emode import EModeCategory
from src.protocol.liquidation import LiquidationModel, LiquidationParams


@dataclass
class VaultPosition:
    """Represents a Mellow vault wstETH/ETH leveraged position on Aave V3."""

    collateral_amount: float  # wstETH amount
    debt_amount: float  # WETH amount
    emode_enabled: bool = True

    def collateral_value(self, provider: PoolDataProvider) -> float:
        """Collateral value in ETH.

        The Aave oracle price for wstETH already incorporates the stETH/ETH
        peg and the wstETH→stETH exchange rate, so we must NOT multiply by
        the peg again.
        """
        price = provider.get_asset_price(WSTETH)
        return self.collateral_amount * price

    def debt_value(self, provider: PoolDataProvider) -> float:
        """Debt value in ETH."""
        return self.debt_amount * provider.get_asset_price(WETH)

    def net_value(self, provider: PoolDataProvider) -> float:
        """Net position value (equity) in ETH."""
        return self.collateral_value(provider) - self.debt_value(provider)

    def get_liquidation_model(
        self, provider: PoolDataProvider
    ) -> LiquidationModel:
        """Build a LiquidationModel for this position."""
        liq_params_data = provider.get_liquidation_params(WSTETH)
        liq_params = LiquidationParams(
            ltv=liq_params_data.ltv,
            liquidation_threshold=liq_params_data.liquidation_threshold,
            liquidation_bonus=liq_params_data.liquidation_bonus,
        )
        emode: EModeCategory | None = None
        if self.emode_enabled:
            emode = provider.get_emode_category(EMODE_ETH_CORRELATED)
        return LiquidationModel(liq_params, emode=emode)

    def health_factor(self, provider: PoolDataProvider) -> float:
        """Current health factor."""
        model = self.get_liquidation_model(provider)
        return model.health_factor(
            self.collateral_value(provider), self.debt_value(provider)
        )

    def leverage_with_prices(self, provider: PoolDataProvider) -> float:
        """Leverage using actual ETH values."""
        net = self.net_value(provider)
        if net <= 0:
            return float("inf")
        return self.collateral_value(provider) / net
