## Background

We are creating a mock risk dashboard for a wstETH/ETH borrowing position. 

For the purpose of the demo we will look at the WETH borrowing market on Aave and take a borrowing Position from a vault (Mellow) as an example.

## Model the Aave Protocol

- code to model how liquidation works
- how rates are calculated
- get the parameters of the WETH pool (oracle, LLTV, liquidation penalty, interest rate model params)

## Simulate liquidations

- ETH price Brownian motion based on latest volatility
- Look where ETH is used as collateral to borrow assets like stables. is there a risk that ETH supply is removed because ETH is liquidated.
- Understand the oracle is 1:1 for ETH vs StetH in Aave so no liquidation risk for the borrowers.
- Model also the utilization rate of the WETH/ETH pool which probabilistic distribution does it follow, what are the main drivers. From utilization rate, we model the interest rate. Is there a correlation with changes in ETH prices or vol.
- Add the impact of WETH liquidated on WETH supply.
- Model the stETH/ETH depeg and its future changes.
    - Update it with potential unwinds when borrowing spread becomes negative
    - is there a relationship between people unwinding their position and leverage and stETH depeg, ETH volatility
- Source the slippage amount of users selling stETH to unwind their positions
- stETH can also be borrowed also utilisation is very small but this will add a few bps to the strategy APY. Need to model this.

**Output:** 

- Current APY and an interval of confidence regarding how much it will be over next day

- Var 95 and risk metrics for the P&L of the position mostly due to the price of stETH depegging
- Calculate the cost to unwind X % of the portfolio average and var95 taking into account changes in stETH volatility, gas costs, market liquidity.

## Stress Tests

- identify a few historical stress tests and calculate the position performance
- look at a stress test based on ETH down 20% looking at stressed correlations and betas
