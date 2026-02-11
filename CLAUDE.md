# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

wstETH/ETH Risk Dashboard for Aave V3 — models a Mellow vault leveraged position (wstETH collateral, WETH debt) with Monte Carlo simulations, liquidation cascades, and stress testing.

## Commands

```bash
# Install
uv pip install -e ".[dev]"

# Install with on-chain data support (optional)
uv pip install -e ".[dev,onchain]"

# Run all tests
uv run pytest

# Run a specific test file
uv run pytest tests/protocol/test_interest_rate.py

# Run a specific test class or method
uv run pytest tests/protocol/test_interest_rate.py::TestVariableBorrowRate::test_rate_at_zero_utilization

# Run live on-chain integration tests (requires ETH_RPC_URL)
ETH_RPC_URL=... uv run pytest -m onchain

# Run dashboard
uv run streamlit run src/dashboard/app.py
```

No linter or formatter is configured.

## Architecture

All values are denominated in ETH. The codebase uses `src.*` imports (pythonpath is `.`).

**`src/data/`** — Abstract `PoolDataProvider` interface, `StaticDataProvider` with hardcoded parameters, and `OnChainDataProvider` fetching live Aave V3 data via web3.py (`contracts.py` for addresses/ABIs, `onchain_provider.py` for the provider, `provider_factory.py` for selection logic). `web3` is an optional dependency; the project works without it.

**`src/protocol/`** — Aave V3 mechanics: piecewise-linear kinked interest rate model (`InterestRateModel`), pool state with non-mutating simulation methods (`PoolModel`), liquidation logic with E-mode support (`LiquidationModel`).

**`src/position/`** — `VaultPosition` represents the leveraged position. `pnl.py` computes APY breakdown (staking + supply income vs borrow cost). `unwind.py` has both a simple backward-compatible `estimate_unwind_cost()` and a detailed AMM constant-product price impact model.

**`src/simulation/`** — Monte Carlo engine using Ornstein-Uhlenbeck utilization paths (Euler-Maruyama discretization) with vectorized borrow rate computation. Liquidation cascade simulator iterates: liquidate → seize collateral → recompute rate → estimate at-risk debt.

**`src/stress/`** — Three historical stress scenarios (June 2022 stETH depeg, March 2020 Black Thursday, May 2022 Terra/Luna). Shock engine applies scenarios to positions. Cholesky-based correlated scenario generation. VaR/CVaR computation from MC results.

**`src/dashboard/`** — Streamlit app with 5 tabs: Overview, Interest Rates, Liquidation Analysis, Simulations, Stress Tests. Charts use Plotly with `plotly_dark` template. Sidebar params flow through `SidebarParams` dataclass.

## Key Patterns

- **Frozen dataclasses** for all parameter/config containers (`InterestRateParams`, `LiquidationParams`, `OUParams`, `StressScenario`, etc.)
- **Non-mutating simulations** — pool/cascade methods return result dicts/dataclasses, never modify input state
- **Provider abstraction** — `PoolDataProvider` ABC allows swapping static data for live RPC in the future
- **E-mode** — `LiquidationModel` accepts optional `EModeCategory` which overrides standard LTV/threshold/bonus (E-mode 1: LTV 93.5%, threshold 95.5%, bonus 1%)

## Key Formulas

- Health Factor: `HF = (collateral_value × liquidation_threshold) / debt_value`
- Borrow Rate (below kink): `base_rate + (utilization / optimal_utilization) × slope1`
- Borrow Rate (above kink): `base_rate + slope1 + ((utilization - optimal) / (1 - optimal)) × slope2`
- Net APY: `(collateral_val × (staking_apy + supply_apy) - debt_val × borrow_apy) / equity`
