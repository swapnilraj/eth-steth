"""APY breakdown and P&L calculations for the vault position."""

from dataclasses import dataclass

from src.data.constants import WETH, WSTETH
from src.data.interfaces import PoolDataProvider
from src.position.vault_position import VaultPosition
from src.protocol.interest_rate import InterestRateModel
from src.protocol.pool import PoolState


@dataclass(frozen=True)
class APYBreakdown:
    """Breakdown of position APY components."""

    supply_apy: float  # wstETH supply APY on Aave
    borrow_apy: float  # WETH borrow APY on Aave
    staking_apy: float  # Lido staking rewards (embedded in wstETH)
    net_apy: float  # Combined APY on equity


def compute_apy_breakdown(
    position: VaultPosition,
    provider: PoolDataProvider,
    staking_apy: float = 0.035,  # ~3.5% Lido staking yield
) -> APYBreakdown:
    """Compute APY breakdown for the vault position.

    Args:
        position: The vault position.
        provider: Data provider for pool state and params.
        staking_apy: Annual staking reward rate for stETH.

    Returns:
        APYBreakdown with all components.
    """
    # wstETH supply rate on Aave
    wsteth_params = provider.get_reserve_params(WSTETH)
    wsteth_state = provider.get_reserve_state(WSTETH)
    wsteth_pool = PoolState.from_reserve_state(wsteth_state)
    wsteth_rate_model = InterestRateModel(wsteth_params)
    supply_apy = wsteth_rate_model.supply_rate(wsteth_pool.utilization)

    # WETH borrow rate
    weth_params = provider.get_reserve_params(WETH)
    weth_state = provider.get_reserve_state(WETH)
    weth_pool = PoolState.from_reserve_state(weth_state)
    weth_rate_model = InterestRateModel(weth_params)
    borrow_apy = weth_rate_model.variable_borrow_rate(weth_pool.utilization)

    # Net APY on equity
    collateral_val = position.collateral_value(provider)
    debt_val = position.debt_value(provider)
    equity = collateral_val - debt_val

    if equity <= 0:
        net_apy = float("-inf")
    else:
        # Income: staking yield on collateral + supply yield on collateral
        # Cost: borrow rate on debt
        income = collateral_val * (staking_apy + supply_apy)
        cost = debt_val * borrow_apy
        net_apy = (income - cost) / equity

    return APYBreakdown(
        supply_apy=supply_apy,
        borrow_apy=borrow_apy,
        staking_apy=staking_apy,
        net_apy=net_apy,
    )


@dataclass(frozen=True)
class PnLDecomposition:
    """Detailed P&L decomposition with basis and break-even analysis."""

    staking_income_daily: float   # ETH/day from staking yield
    supply_income_daily: float    # ETH/day from Aave supply yield
    borrow_cost_daily: float      # ETH/day borrow cost
    net_carry_daily: float        # Net daily carry (income - cost)
    basis_spread: float           # staking_apy - borrow_apy
    break_even_peg_drop: float    # Max peg drop before carry turns negative annualized


def daily_pnl(
    position: VaultPosition,
    provider: PoolDataProvider,
    staking_apy: float = 0.035,
) -> float:
    """Estimate daily P&L in ETH for the position.

    Returns income minus cost regardless of whether equity is positive or
    negative.  An underwater position still accrues borrow interest (and
    earns staking yield), so the daily P&L should stay negative rather
    than flat-lining at zero.
    """
    breakdown = compute_apy_breakdown(position, provider, staking_apy)
    collateral_val = position.collateral_value(provider)
    debt_val = position.debt_value(provider)
    income = collateral_val * (staking_apy + breakdown.supply_apy)
    cost = debt_val * breakdown.borrow_apy
    return (income - cost) / 365.25


def pnl_decomposition(
    position: VaultPosition,
    provider: PoolDataProvider,
    staking_apy: float = 0.035,
) -> PnLDecomposition:
    """Compute detailed P&L decomposition with basis spread analysis.

    Args:
        position: The vault position.
        provider: Data provider for pool state and params.
        staking_apy: Annual staking reward rate.

    Returns:
        PnLDecomposition with carry breakdown and break-even analysis.
    """
    breakdown = compute_apy_breakdown(position, provider, staking_apy)
    collateral_val = position.collateral_value(provider)
    debt_val = position.debt_value(provider)

    staking_income = collateral_val * staking_apy / 365.25
    supply_income = collateral_val * breakdown.supply_apy / 365.25
    borrow_cost = debt_val * breakdown.borrow_apy / 365.25
    net_carry = staking_income + supply_income - borrow_cost

    # Basis spread: difference between staking yield and borrow cost rate
    basis_spread = staking_apy - breakdown.borrow_apy

    # Break-even peg drop: how much the exchange rate can drop (annually)
    # before the position's net carry turns negative.
    # Net carry = collateral × (staking + supply) - debt × borrow
    # If peg drops by X, collateral_val drops by X × collateral_val
    # Break-even: net_carry_annual = X × collateral_val
    net_carry_annual = (staking_income + supply_income - borrow_cost) * 365.25
    if collateral_val > 0:
        break_even = net_carry_annual / collateral_val
    else:
        break_even = 0.0

    return PnLDecomposition(
        staking_income_daily=staking_income,
        supply_income_daily=supply_income,
        borrow_cost_daily=borrow_cost,
        net_carry_daily=net_carry,
        basis_spread=basis_spread,
        break_even_peg_drop=max(0.0, break_even),
    )
