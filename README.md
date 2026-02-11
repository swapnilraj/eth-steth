# wstETH/ETH Risk Dashboard

Risk analytics dashboard for a leveraged wstETH/ETH position on Aave V3, modeled after a Mellow vault strategy.

## What it does

- **Protocol modeling** — Aave V3 interest rate curves (kinked linear), liquidation mechanics, health factor, E-mode support
- **Position analysis** — APY breakdown (staking yield + supply APY − borrow cost), leverage, daily P&L
- **Monte Carlo simulation** — Ornstein-Uhlenbeck utilization paths, vectorized rate computation, cumulative P&L tracking, liquidation probability
- **Liquidation cascades** — Iterative simulation: liquidate debt → seize collateral → rate spike → new at-risk debt
- **Stress testing** — 3 historical scenarios (June 2022 stETH depeg, March 2020 Black Thursday, May 2022 Terra/Luna), custom scenario builder, Cholesky-correlated shocks
- **Risk metrics** — VaR (95/99), CVaR, max loss, liquidation probability
- **Unwind cost** — Constant-product AMM price impact model, gas estimation, size sensitivity

## Quick start

```bash
# Install dependencies
uv pip install -e ".[dev]"

# Run tests
uv run pytest

# Launch dashboard
uv run streamlit run src/dashboard/app.py
```

## Dashboard

Five tabs:

| Tab | Content |
|-----|---------|
| **Position Overview** | Health factor, net APY, leverage, daily P&L, equity breakdown |
| **Interest Rates** | WETH/wstETH rate curves, sensitivity table, borrow impact simulator |
| **Liquidation Analysis** | HF gauge, distance to liquidation, depeg sensitivity chart |
| **Simulations** | Monte Carlo fan charts, P&L distribution, cascade waterfall, unwind cost |
| **Stress Tests** | Historical scenarios, custom builder, VaR/CVaR, correlated shock scatter |

## Project structure

```
src/
├── protocol/          # Aave V3 mechanics (rates, pool, liquidation, E-mode)
├── position/          # Vault position, P&L, unwind cost
├── simulation/        # Monte Carlo engine, liquidation cascades
├── stress/            # Scenarios, shock engine, VaR/CVaR
├── data/              # Abstract provider interface, static Aave V3 params
└── dashboard/         # Streamlit app, pages, chart components
```

## Default position

The dashboard defaults to a representative Mellow vault position:

- **Collateral:** 12,000 wstETH @ 1.18 ETH = 14,160 ETH
- **Debt:** 10,500 WETH
- **E-mode:** Enabled (LTV 93.5%, liquidation threshold 95.5%)
- **Health Factor:** ~1.29
- **Leverage:** ~3.87x

## Tech stack

Python 3.11+ · Streamlit · Plotly · NumPy · Pandas · pytest
