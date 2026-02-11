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

## 13. Liquidation Cascade Can No Longer Cascade

- **Code:** `src/simulation/liquidation_cascade.py:73-121`
- **Issue:** After fixing the WETH pool mechanics, every liquidation *reduces* rates, so `rate_change_pct` is ≤ 0 and `at_risk_debt = max(0, ...)` becomes zero in the first loop iteration. The "cascade" always stops after one step.
- **Impact:** Dashboard promises cascade analysis, but it is impossible to get more than a single step regardless of inputs.
- **Fix:** Redesigned cascade to be driven by **price impact** instead of rate changes. Selling seized wstETH depresses the peg → more positions breach HF → new at-risk debt. Replaced `rate_sensitivity` with `price_impact_per_unit` and `depeg_sensitivity` parameters. The cascade now correctly propagates through the peg-impact feedback loop.
- **Status:** Fixed.

## 14. Liquidation Probability Chart Uses Stale Logic

- **Code:** `src/dashboard/components/charts.py:252-301`
- **Issue:** Still infers liquidation from cumulative min P&L even though Monte Carlo now liquidates via HF checks (`HF = collateral × threshold / debt`). Equity-positive paths can liquidate and will never be counted; equity-negative but safe paths can be counted erroneously.
- **Impact:** The "Cumulative Liquidation Probability" visualization disagrees with the real Monte Carlo `liquidated` flag.
- **Fix:** Added `hf_paths` to `MonteCarloResult`. Chart now uses `np.minimum.accumulate(mc_result.hf_paths)` and checks `cum_min_hf < 1.0` at each step.
- **Status:** Fixed.

## 15. Stress Scenario Utilization/Duration Controls Are No-Ops

- **Code:** `src/stress/shock_engine.py:40-80`, `src/dashboard/tabs/stress_tests.py:62-139`
- **Issue:** `StressScenario.utilization_shock` and `duration_days` (and the UI sliders for them) never flow into `apply_scenario`; only the peg is used.
- **Impact:** Users believe they are stressing utilization/duration, but these inputs have zero effect on HF/P&L.
- **Fix:** Dashboard now computes full period P&L: `peg_P&L + staking_income − borrow_cost` where `borrow_cost = debt × stressed_rate(utilization_shock) × duration/365`. Both historical and custom scenarios reflect borrow costs.
- **Status:** Fixed.

## 16. Correlated VaR Still Treats P&L as Collateral Shock

- **Code:** `src/stress/var.py:66-94`
- **Issue:** `compute_var_from_scenarios` sets `stressed_collateral = collateral_value + pnl_array`. The correlated P&L already mixes collateral moves with debt growth (borrow cost, staking income), so subtracting it from collateral both double counts peg shocks and misclassifies pure cost shocks as collateral losses.
- **Impact:** Reported liquidation probability for correlated VaR can show liquidations driven purely by borrow-cost stress even when collateral value never moved.
- **Fix:** `compute_var_from_scenarios` now accepts optional `stressed_collateral_array` and `stressed_debt_array` for proper per-scenario HF computation. The correlated scenario loop tracks collateral and debt separately.
- **Status:** Fixed.

## 17. ETH Price Change Inputs Are No-Ops

- **Code:** `src/stress/scenarios.py:13-24`, `src/dashboard/tabs/stress_tests.py:62-139`, `src/stress/shock_engine.py:40-80`
- **Issue:** Both historical scenarios and the custom scenario builder expose an `eth_price_change` field (UI slider + table column), but `apply_scenario()` ignores it entirely—it only rescales collateral by `scenario.steth_peg`.
- **Impact:** Users are misled into thinking ETH drawdowns are included when, in reality, the stress outputs only reflect peg moves.
- **Fix:** Removed the no-op "ETH Price Change (%)" slider from the custom scenario builder. Added an explanatory caption that ETH/USD moves don't affect ETH-denominated positions' HF. Historical table already omitted the column (previous fix). The `eth_price_change` field remains in `StressScenario` for reference but is no longer presented as a controllable input.
- **Status:** Fixed.

## 18. Correlated Scenarios Ignore the Current Peg Baseline

- **Code:** `src/stress/shock_engine.py:122-131`, `src/dashboard/tabs/stress_tests.py:30-78`
- **Issue:** `generate_correlated_scenarios()` always centres peg shocks around 1.0 (`result[:, 1] = np.clip(1.0 + shocks[:, 1], ...)`) and the correlated VaR logic treats those as absolute peg levels. When the dashboard is already operating with a non-unit peg (via the sidebar slider or live data), section 4 still re-pegs collateral back to 1.0 in "neutral" scenarios.
- **Impact:** Correlated VaR exaggerates positive P&L and understates liquidation risk whenever the actual peg ≠ 1.0.
- **Fix:** `generate_correlated_scenarios` now accepts `base_peg` and `base_utilization` parameters to centre shocks around the current market values. The dashboard passes `current_peg` and `weth_state.utilization`.
- **Status:** Fixed.

---

All eighteen items are now fixed.
