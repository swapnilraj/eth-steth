# Mathematical + Protocol Fidelity Issues

This repo aims to mirror Aave V3 + the Mellow vault mechanics, but several core calculations diverge from the protocol. Each section below cites the offending code, explains why it is wrong, and describes the downstream impact.

## 1. Pool Utilization Formula Is Wrong

- **Code:** `src/protocol/pool.py:12-38`, `src/protocol/pool.py:47-88`
- **Issue:** Utilization was computed as `total_debt / (total_supply + total_debt)` and borrows reduced `total_supply`. This double-counted debt and pushed the baseline utilization from the true ~78% down to ~44%.
- **Impact:** All rate readouts, Monte Carlo OU defaults, and borrow-impact charts were wrong. (**Status:** Fixed.)

## 2. Collateral Value Double-Counted the stETH Peg

- **Code:** `src/position/vault_position.py:33-37`
- **Issue:** Multiplied the wstETH oracle price by `get_steth_eth_peg()` even though the oracle already includes that peg, squaring peg shocks.
- **Impact:** Health factor, leverage, APY, and stress metrics understated collateral when using real data or the peg slider. (**Status:** Fixed.)

## 3. Stress Tests Applied ETH/USD Moves to an ETH-Denominated Position

- **Code:** `src/stress/shock_engine.py:61-70`, `src/dashboard/tabs/stress_tests.py:33-140`
- **Issue:** Historical/custom scenarios scaled collateral by `(1 + eth_price_change)` *and* by the peg, even though both collateral and debt are in ETH. A USD ETH crash shouldn't change the HF.
- **Impact:** Stress/VaR tabs massively overstated liquidations during ETH sell-offs. (**Status:** Fixed.)

## 4. Monte Carlo Treated Borrow Interest as Collateral Loss

- **Code:** `src/simulation/monte_carlo.py:136-156`
- **Issue:** Debt stayed flat while borrow interest was subtracted from collateral. In Aave, debt grows via interest and collateral stays intact unless you unwind.
- **Impact:** P&L distribution and liquidation probability were disconnected from reality. (**Status:** Fixed.)

## 5. Liquidation Cascade Operates on a Fictitious Single Pool

- **Code:** `src/simulation/liquidation_cascade.py:68-106`
- **Issue:** Collateral seized in wstETH was subtracted from the WETH pool supply, which makes no sense—collateral belongs to the wstETH pool.
- **Impact:** Cascade utilization/rate path was impossible. (**Status:** Fixed.)

## 6. Borrow Impact Simulator Mutated Supply

- **Code:** `src/protocol/pool.py:47-69`
- **Issue:** Simulating a borrow reduced total supply even though aToken supply is unchanged; only available liquidity falls.
- **Impact:** "Borrow Impact" tab understated rate jumps. (**Status:** Fixed.)

## 7. Depeg Slider Monkey-Patched Peg Twice

- **Code:** `src/dashboard/app.py:57-77`
- **Issue:** Overrode both `get_asset_price` and `get_steth_eth_peg`, scaling the same peg twice when on-chain data was in use.
- **Impact:** Interactive peg shocks exaggerated collateral loss. (**Status:** Fixed.)

## 8. Correlated Scenarios Ignored Utilization Shocks

- **Code:** `src/dashboard/tabs/stress_tests.py:203-214`
- **Issue:** `generate_correlated_scenarios` returned `(eth_change, peg, utilization)`, but the utilization column was discarded, so borrow-rate stress never appeared in correlated VaR.
- **Impact:** VaR misssed the cost-side risk from utilization spikes. (**Status:** Fixed.)

## 9. Correlated VaR Used a Dummy Liquidation Proxy

- **Code:** `src/stress/var.py:80-82`
- **Issue:** Liquidation probability was approximated by "fraction of scenarios with P&L < -mean|P&L|," ignoring HF mechanics.
- **Impact:** Reported liquidation risk had no relation to Aave behaviour. (**Status:** Fixed.)

## 10. `simulate_liquidation_impact` Mixed Collateral & Debt Pools

- **Code:** `src/protocol/pool.py:90-113`
- **Issue:** Reduced both supply and debt within one pool even though debt repayments only affect WETH debt; collateral seizure affects the separate wstETH pool.
- **Impact:** Produced impossible utilization/rate after a liquidation. (**Status:** Fixed.)

## 11. `VaultPosition.leverage` Compared Different Units

- **Code:** `src/position/vault_position.py:20-31`
- **Issue:** Computed leverage as `wstETH / (wstETH - WETH)` without converting to ETH.
- **Impact:** Anyone using the property saw a bogus ~8× leverage instead of the true ~3.9×. (**Status:** Fixed; dashboard now uses `leverage_with_prices`.)

## 12. Utilization Hard-Coded to 0.44 in Multiple Modules

- **Code:** `src/simulation/monte_carlo.py:20`, `src/stress/shock_engine.py:128-129`, `src/dashboard/components/sidebar.py:64-79`
- **Issue:** Defaults baked in the wrong 0.44 utilization even after pool math was fixed, biasing simulations toward low rates.
- **Impact:** Monte Carlo and correlated scenarios centred on a false baseline. (**Status:** Fixed.)

## 13. Peg Shocks Are Applied Directly to the Aave Oracle

- **Code:** `src/protocol/liquidation.py:33-134`, `src/stress/shock_engine.py:40-74`, `src/dashboard/tabs/liquidation.py:21-95`
- **Issue:** Modelling a protocol-level exchange-rate shock (e.g. Lido slashing) by scaling the wstETH oracle is intentional for what-if analysis; not a protocol bug. (**Status:** Fixed/expected behaviour.)

## 14. Liquidation Probability Chart Ignores `hf_paths`

- **Code:** `src/dashboard/components/charts.py:252-301`, `src/simulation/monte_carlo.py:152-189`
- **Issue:** Now uses `hf_paths` to detect liquidations, so the chart matches the simulation. (**Status:** Fixed.)

## 15. Scenario Utilization & Duration Inputs Are Still Dead

- **Code:** `src/stress/scenarios.py:13-24`, `src/stress/shock_engine.py:40-74`, `src/dashboard/tabs/stress_tests.py:62-194`
- **Issue:** Custom/historical scenarios now feed `utilization_shock` and `duration_days` into borrow-cost calculations. (**Status:** Fixed.)

## 16. ETH Price Change Controls Do Nothing

- **Code:** `src/stress/scenarios.py`, `src/dashboard/tabs/stress_tests.py`
- **Issue:** ETH-price sliders were removed because ETH/USD moves do not affect HF; remaining fields are informational. (**Status:** Fixed.)

## 17. Correlated Scenarios Drop the ETH Dimension

- **Code:** `src/stress/shock_engine.py:82-135`, `src/dashboard/tabs/stress_tests.py:220-258`
- **Issue:** `_eth_change` in correlated scenarios is still discarded, so ETH/peg correlation inputs have no effect.
- **Impact:** The “correlated shock analysis” is really just peg + utilization.

## 18. Monte Carlo Continues Accruing After Liquidation

- **Code:** `src/simulation/monte_carlo.py:152-189`
- **Issue:** Balances are now frozen at the first HF<1.0 timestep so post-liquidation accruals stop. (**Status:** Fixed.)

## 19. Cascade `at_risk_debt` Off by 100×

- **Code:** `src/simulation/liquidation_cascade.py:108-109`
- **Issue:** `depeg_pct = peg_drop * 100.0` converted the fractional peg drop to percentage points, then `at_risk_debt = debt * depeg_sensitivity * depeg_pct` multiplied by that percentage-point value. Net effect was 100× too much at-risk debt.
- **Impact:** Cascades wiped out the entire pool in 2 steps. (**Status:** Fixed.)

## 20. Cascade `peg_drop` Unbounded — Can Exceed 100%

- **Code:** `src/simulation/liquidation_cascade.py:97`
- **Issue:** `peg_drop = collateral_seized * price_impact_per_unit` had no upper bound, so a big liquidation could drive the modeled peg negative before the hard floor kicked in.
- **Impact:** Cascade produced impossible negative prices mid-simulation. (**Status:** Fixed.)

## 21. Scenario P&L Double Counts Slashing Losses

- **Code:** `src/dashboard/tabs/stress_tests.py:102-150`
- **Issue:** Table/metric P&L adds `shock.pnl_impact` (exchange-rate hit) and then accrues staking income on the *pre-stress* collateral value (`collateral_val`). After a slash, the staking base should be the stressed collateral. As written, income is overstated whenever the exchange-rate factor < 1.
- **Impact:** Stress P&L (historical + custom) is biased high following a slashing event.

## 22. Correlated ETH Shocks Still Ignored

- **Code:** `src/dashboard/tabs/stress_tests.py:223-251`
- **Issue:** `generate_correlated_scenarios` outputs `(eth_change, peg, utilization)` but `_eth_change` is thrown away, so ETH volatility/correlation never influence P&L or VaR.
- **Impact:** Section 4 still models only peg/utilization, despite claiming tri-variate shocks.

## 23. `simulate_withdrawal` Allows Negative Utilization

- **Code:** `src/protocol/pool.py:74-93`
- **Issue:** If a caller simulates withdrawing more than the total supply, `new_supply` becomes negative and the returned utilization flips sign. Utilization should be clamped to [0,1] by capping `new_supply` at zero.
- **Impact:** Borrow-impact and sensitivity analyses can report nonsensical negative utilization if a user enters an outsized withdrawal.

---

Issues 17, 21, 22, and 23 remain outstanding; the rest are fixed.
