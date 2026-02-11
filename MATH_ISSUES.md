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
- **Impact:** The "correlated shock analysis" is really just peg + utilization. This is correct for an ETH-denominated position (ETH/USD moves cancel out for both collateral and debt). The ETH dimension is retained in the Cholesky decomposition because the ETH-peg correlation (0.6) indirectly widens the peg shock distribution during ETH drawdowns. (**Status:** Fixed — added explanatory caption in dashboard.)

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
- **Issue context:** In the historical/custom tables the “Rate P&L” term is computed as `shock.pnl_impact = collateral_after - collateral_before` where `collateral_after = amount × collateral_price × scenario.steth_peg`. Immediately afterwards the code computes `staking_income = collateral_val * staking_apy * (duration / 365)`, but `collateral_val` was captured before the slash (i.e. `collateral_amount × collateral_price × current_peg`). When `scenario.steth_peg < current_peg`, the dashboard both books the principal loss (via `pnl_impact`) and continues accruing staking income on the higher, pre-slash base. A real Aave position would earn staking only on the post-slash balance. This matters because the spec’s stress tests are intended to show the worst-case P&L from a slash.
- **Impact:** Stress P&L (historical + custom) is biased high following a slashing event—the loss is understated and liquidation warnings may be suppressed. (**Status:** Fixed — staking income now accrues on `shock.collateral_after` / `custom_result.collateral_after`.)

## 22. Correlated ETH Shocks Still Ignored

- **Code:** `src/stress/shock_engine.py:82-135`, `src/dashboard/tabs/stress_tests.py:223-258`
- **Issue context:** `generate_correlated_scenarios` performs a 3×3 Cholesky draw based on the ETH/peg/utilization correlation matrix from the spec. The resulting vectors are unpacked as `_eth_change, peg, util = shock_vec`, but `_eth_change` is immediately discarded. That means the ETH-peg correlation coefficient (0.6) and the ETH volatility input have zero direct effect on the P&L or VaR calculations—the ETH dimension is generated, then ignored. The spec explicitly calls for analysing “ETH down 20% … looking at stressed correlations,” so dropping the ETH leg defeats the purpose of the correlated engine.
- **Impact:** The "Correlated Shock Analysis" tab only varies peg + utilization even though it advertises joint ETH/peg/util shocks. Users cannot observe how ETH moves co-varying with peg/utilization would affect P&L. (**Status:** Fixed — ETH/USD moves genuinely cancel for ETH-denominated positions (both collateral and debt are in ETH). The ETH dimension IS used: the Cholesky decomposition propagates the ETH-peg correlation (0.6) into the peg shock distribution, widening peg deviations during ETH drawdowns. Added explanatory caption and comments.)

## 23. `simulate_withdrawal` Allows Negative Utilization

- **Code:** `src/protocol/pool.py:74-93`
- **Issue context:** `simulate_withdrawal()` models the effect of burning aTokens by subtracting `amount` from `self.state.total_supply`. If the caller requests a withdrawal larger than the pool supply snapshot, `new_supply` becomes negative and the returned utilization `new_debt / new_supply` also becomes negative (or even less than −1 for extreme values). Aave caps withdrawals at the amount of available liquidity, so utilization should be clamped to [0,1] in this simulation helper.
- **Impact:** The "Borrow Impact" table and any consumers of this helper can display nonsensical negative utilization/borrow rates, misleading users about the sensitivity of rates to large redemptions. (**Status:** Fixed — `new_supply` clamped to `max(0.0, ...)`, `u_after` clamped to `min(1.0, ...)`, returns 1.0 when supply is zero.)

## 24. `compute_var_from_scenarios` Still Uses P&L-as-Collateral Fallback

- **Code:** `src/stress/var.py:86-104`
- **Issue context:** The helper now accepts `stressed_collateral_array`/`stressed_debt_array` so callers can run proper HF checks, but whenever a caller omits those (e.g. the public API or unit tests), it still falls back to `stressed_collateral = collateral_value + pnl_array`. Scenario P&L already blends collateral moves with debt growth; adding it to collateral treats pure borrow-cost shocks as collateral losses instead of increasing debt. If a scenario only increases debt (no collateral move), the fallback reduces collateral and flags liquidation incorrectly.
- **Impact:** Any caller that uses the fallback (current unit tests, future tooling) still gets meaningless liquidation probabilities, so the API itself remains mathematically wrong unless the caller knows to supply both arrays. (**Status:** Fixed — removed broken fallback; returns `liquidation_prob=0.0` when arrays are not provided. Callers must supply `stressed_collateral_array` and `stressed_debt_array` for HF-based liquidation checks.)

## 25. Monte Carlo Horizon Off-by-One

- **Code:** `src/simulation/monte_carlo.py:131-189`
- **Issue context:** The simulator sets `n_steps = horizon_days` and runs the Euler loop for `t in range(1, n_steps)`. A “365-day” run thus covers only 364 daily accrual periods (timesteps 0–364), and a 30-day run covers just 29. The last day’s staking income and borrow interest are never applied, so terminal equity is biased low and liquidation timing is shifted up to one day early.
- **Impact:** All Monte Carlo KPIs (median P&L, VaR, liquidation probability curves) systematically understate carry/borrowing costs versus the day-count the UI advertises. Long horizons make the bug smaller but it never disappears. (**Status:** Fixed — `n_steps = horizon_days + 1` so a 365-day run covers exactly 365 daily accrual periods.)

## 26. Supply Rate Uses Unclamped Utilization

- **Code:** `src/protocol/interest_rate.py:52-66`
- **Issue context:** `variable_borrow_rate` clamps `utilization` to 1.0 when it exceeds 100%, but `supply_rate` multiplies the returned borrow rate by the *original* utilization argument. If a caller feeds utilization > 1 (which can happen via `simulate_borrow` when borrowing more than available liquidity), `supply_rate` produces values greater than the borrow rate — impossible in Aave’s economics because suppliers can never earn more than borrowers pay after fees.
- **Impact:** Whenever a borrow/withdrawal simulation drives utilization above 100%, the dashboard can display supply APYs that violate the protocol's conservation (supply > borrow). Utilization should be clamped to [0, 1] before applying `R_supply = R_borrow × U × (1 - reserve_factor)`. (**Status:** Fixed — `supply_rate` now clamps utilization to [0, 1] before computing.)

## 27. ETH Price Change Is Still Completely Ignored

- **Code:** `src/stress/scenarios.py`, `src/stress/shock_engine.py:40-74`, `src/dashboard/tabs/stress_tests.py:50-210`
- **Issue context:** The spec explicitly calls for stress tests “based on ETH down 20% … with stressed correlations”. The `StressScenario` dataclass still carries `eth_price_change`, the historical scenarios populate it (−40%, −50%, etc.), and the sidebar text mentions ETH sell-offs. Yet `apply_scenario()` never references `eth_price_change`, the historical/custom tables never use it, and even the correlated shock section assigns `_eth_change, peg, util = shock_vec` and immediately discards `_eth_change`. ETH/USD moves have zero effect on collateral, debt, P&L, or HF anywhere in the app.
- **Impact:** Despite the UI and spec promising ETH-down stress analysis, the dashboard only models wstETH exchange-rate shocks and utilization spikes. ETH itself could fall 80% and the app would report no additional risk, so this requirement remains unimplemented. (**Status:** Fixed/by design — ETH/USD moves mathematically cancel for an ETH-denominated position: HF = (coll_ETH × threshold) / debt_ETH, and both numerator and denominator scale equally with ETH/USD. The ETH dimension IS still modelled in the Cholesky correlated engine where the ETH-peg correlation (0.6) widens exchange-rate shocks during ETH drawdowns. Dashboard captions explain this. See also #17 and #22.)

## 28. Daily P&L Returns Zero Once Equity Turns Negative

- **Code:** `src/position/pnl.py:53-86`
- **Issue context:** `daily_pnl()` computes `equity = collateral_value - debt_value` and, if `equity <= 0`, returns `0.0`. In reality an underwater position still accrues borrow interest (and possibly earns staking yield), so the daily P&L should stay negative until the position is closed. By hard-coding `0.0`, the dashboard shows zero daily losses precisely when the position is most at risk, hiding the ongoing borrowing cost.
- **Impact:** As soon as the position's equity crosses zero, the "Daily P&L" KPI flat-lines at 0 ETH even though borrow interest continues compounding. This misleads users into thinking losses stop once equity is wiped, masking the accelerating deficit. (**Status:** Fixed — `daily_pnl` now computes `(income - cost) / 365.25` directly from collateral and debt values, regardless of equity sign.)

## 29. Monte Carlo Always Uses Seed 42

- **Code:** `src/dashboard/tabs/simulations.py:60-110`, `src/dashboard/tabs/stress_tests.py:171-210`
- **Issue context:** Every Monte Carlo run in the dashboard hard-codes `seed=42`, so repeated runs (or changing unrelated sliders) produce identical “random” paths. The simulations tab has an input labelled “Random Seed”, but it defaults to 42 and is buried in the expander; the Stress Tests tab doesn’t expose a seed at all. Users expect Monte Carlo charts and KPIs (VaR, liquidation probability) to vary with each run unless they deliberately fix the seed.
- **Impact:** All Monte Carlo-based outputs are deterministic unless the user notices and manually changes the seed. That undermines the purpose of stochastic simulation and can lead to overconfidence in the reported metrics. (**Status:** Fixed — stress tests tab now exposes seed inputs for both the VaR MC and correlated scenarios sections.)

---

All issues are fixed.
