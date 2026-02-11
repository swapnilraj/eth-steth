# Mathematical + Protocol Fidelity Issues

This repo aims to mirror Aave V3 + the Mellow vault mechanics, but several core calculations diverge from the protocol. Each section below cites the offending code, explains why it is wrong, and describes the downstream impact.

## 1. Pool Utilization Formula Is Wrong

- **Code:** `src/protocol/pool.py:16-22`, `src/protocol/pool.py:47-69`
- **Issue:** Utilization is computed as `total_debt / (total_supply + total_debt)`. When a borrow is simulated, the code *reduces* `total_supply` by the borrowed amount, further distorting utilization.
- **Why it is wrong:** In Aave, `total_supply` (the aToken supply) already equals `available_liquidity + total_debt`, so the canonical utilization is simply `total_debt / total_supply`. Subtracting debt in the denominator double-counts it and yields a much lower utilization (~44 % vs the real ~78 % for WETH), and simulating a borrow should increase debt and reduce **available** liquidity but not the aToken supply.
- **Impact:** Every module that consumes `PoolState.utilization` is wrong: interest-rate readouts (`src/dashboard/tabs/rates.py`), OU defaults in Monte Carlo, the borrow impact simulator, cascade inputs, and any downstream APY calculations. Borrow/supply APYs are understated, and rate sensitivities are meaningless until the utilization math is fixed.
- **Status:** Fixed.

## 2. Collateral Value Double-Counts the stETH Peg

- **Code:** `src/position/vault_position.py:33-37`
- **Issue:** `collateral_value` multiplies the Aave oracle price (`get_asset_price(WSTETH)`) by `get_steth_eth_peg()`.
- **Why it is wrong:** For on-chain data, `get_asset_price(WSTETH)` already includes the Chainlink stETH/ETH feed multiplied by the wstETH↔stETH exchange rate. Calling `get_steth_eth_peg()` (which fetches the same Chainlink feed in `src/data/onchain_provider.py:283-296`) squares the peg shock. A 5 % depeg shows up as ~10 % collateral loss in the dashboard.
- **Impact:** Health factor, leverage, APY, liquidation distance, Monte Carlo inputs, and every stress metric understate collateral whenever the on-chain provider is used or when the user drags the "stETH/ETH Peg" slider (which monkey-patches the same getter). Liquidation warnings trigger far too early.
- **Status:** Fixed.

## 3. Stress Tests Apply USD ETH Moves to an ETH-Denominated Position

- **Code:** `src/stress/shock_engine.py:61-70`, `src/dashboard/tabs/stress_tests.py:203-209`
- **Issue:** Historical and correlated scenarios multiply the **ETH**-denominated wstETH price by `(1 + eth_price_change)` before multiplying by the peg.
- **Why it is wrong:** The position's collateral and debt are both denominated in ETH. A USD move in ETH should have no effect on the health factor unless you explicitly convert to USD or model USD liabilities. The only market variable that should hit the HF is the stETH peg (and debt growth). Applying the ETH/USD move again makes every ETH sell-off look like an additional peg loss.
- **Impact:** Historical scenarios and correlated VaR massively overstate drawdowns and liquidation risk. A 40 % USD crash combined with a 7 % peg break shows up as ~47 % collateral loss even though the borrow is in ETH. The correlated VaR is therefore unusable as a faithful Aave stress metric.
- **Status:** Fixed.

## 4. Monte Carlo Treats Borrow Interest as Collateral Loss Instead of Debt Accrual

- **Code:** `src/simulation/monte_carlo.py:136-156`
- **Issue:** Daily P&L is computed as `collateral_value * staking_apy - debt_value * borrow_rate`, and cumulative P&L is subtracted from collateral when checking liquidation (`collateral_value + pnl < debt_value / threshold`). Debt_value is never increased.
- **Why it is wrong:** On Aave, variable debt tokens accrue interest—the debt balance grows, while collateral stays untouched unless you repay. Modeling interest as a cash drain from collateral double-counts staking income and never grows the debt side, so equity evolves incorrectly.
- **Impact:** Liquidation probabilities and P&L distributions reported in the dashboard are wrong: the engine assumes the borrow interest eats collateral directly, so it both understates how fast HF deteriorates (because debt stays flat) and misstates net carry (because income is treated as immediate collateral accretion). Any VaR derived from this Monte Carlo is therefore disconnected from the real Aave mechanics.
- **Status:** Fixed.

## 5. Liquidation Cascade Operates on a Fictitious Single Pool

- **Code:** `src/simulation/liquidation_cascade.py:68-82`
- **Issue:** The cascade treats debt liquidation and collateral seizure as happening in the same pool: `debt -= debt_to_liquidate` then `supply -= collateral_seized`. In a wstETH/WETH position, debt repayment affects the WETH pool (debt decreases, available liquidity increases, total supply stays the same, utilization drops) while collateral seizure affects the wstETH pool (aToken supply decreases).
- **Why it is wrong:** The cascade subtracts seized collateral from the WETH pool supply, which is nonsensical. WETH pool utilization should always decrease after a liquidation (debt is repaid). The rate-increase feedback loop that drives cascades can never properly fire for cross-asset positions.
- **Impact:** The cascade waterfall chart is based on a pool model that doesn't exist. Cascades appear to propagate when in reality WETH utilization drops after each liquidation step.
- **Status:** Fixed.

## 6. Collateral Seizure Ignores wstETH/ETH Price Conversion

- **Code:** `src/simulation/liquidation_cascade.py:69`
- **Issue:** `collateral_seized = debt_to_liquidate * (1.0 + config.liquidation_bonus)` assumes 1:1 conversion between debt (WETH) and collateral (wstETH).
- **Why it is wrong:** Aave computes seized collateral as `(debt_repaid × debt_price × (1 + bonus)) / collateral_price`. Since wstETH ≈ 1.18 ETH, the seized wstETH amount should be `debt / 1.18 × (1 + bonus)`, not `debt × (1 + bonus)`. Collateral seized is overstated by ~18 %.
- **Impact:** Amplifies the (already-incorrect) pool state changes in the cascade. Combined with bug #5, the cascade is doubly wrong.
- **Status:** Fixed.

## 7. Monte Carlo Omits Supply APY Income

- **Code:** `src/simulation/monte_carlo.py:139`
- **Issue:** MC income is `collateral_value * staking_apy / 365`, but `src/position/pnl.py:61` computes income as `collateral_val * (staking_apy + supply_apy)`. The MC only models staking yield, omitting the Aave supply interest earned on deposited wstETH.
- **Why it is wrong:** The position earns both Lido staking yield AND Aave supply interest. The MC systematically understates income. For a typical position, supply APY adds ~0.01–0.05 %, which compounds over the 365-day horizon.
- **Impact:** P&L distribution is shifted downward, liquidation probabilities and VaR are slightly too pessimistic.
- **Status:** Fixed.

## 8. Correlated Scenarios Generate but Ignore Utilization Shocks

- **Code:** `src/dashboard/tabs/stress_tests.py:203-208`
- **Issue:** `generate_correlated_scenarios` produces a 3-column array `[eth_change, peg, utilization]` via Cholesky decomposition, but the utilization column is completely ignored in the P&L calculation. The code does `eth_change, peg, util = shock_vec` then never uses `util`.
- **Why it is wrong:** Utilization shocks affect borrow rates, which affect the cost leg of P&L. A utilization spike to 0.98 pushes borrow rates from ~2.7 % to >40 % (above the kink). Ignoring utilization makes the correlated VaR capture only collateral-side risk and miss borrow-rate tail risk entirely.
- **Impact:** Correlated VaR understates risk for scenarios where utilization spikes concurrently with ETH crashes and depegs.
- **Status:** Fixed.

## 9. `compute_var_from_scenarios` Uses Arbitrary Liquidation Proxy

- **Code:** `src/stress/var.py:80-82`
- **Issue:** Liquidation probability is defined as `fraction of P&L worse than -mean(|P&L|)`. This is a statistical artifact with no connection to whether HF would drop below 1.0.
- **Why it is wrong:** Liquidation depends on `(collateral + pnl) × liq_threshold < debt`. The proxy knows nothing about collateral, debt, or the liquidation threshold. The number it produces is meaningless as a liquidation probability.
- **Impact:** The correlated VaR section's implied liquidation risk is disconnected from actual Aave liquidation mechanics.
- **Status:** Fixed.

## 10. `simulate_liquidation_impact` Confuses Pool Effects

- **Code:** `src/protocol/pool.py:90-113`
- **Issue:** Reduces both supply and debt in the same `PoolState`. For a wstETH/WETH liquidation, WETH pool debt decreases but supply stays the same (repaid WETH returns to available liquidity). The wstETH pool supply decreases (collateral seized) but its debt is unaffected.
- **Why it is wrong:** Mixing two pools into one computes an impossible utilization.
- **Impact:** Any code using `simulate_liquidation_impact` gets wrong utilization and wrong rates after liquidation events.
- **Status:** Fixed.

## 11. `leverage` Property Compares Different Units

- **Code:** `src/position/vault_position.py:20-31`
- **Issue:** `collateral_amount / (collateral_amount - debt_amount)` divides wstETH by (wstETH − WETH) without price conversion. For 12,000 wstETH and 10,500 WETH: result is 8.0×, correct answer (using prices) is ~3.87×.
- **Why it is wrong:** wstETH ≠ WETH. The property compares apples to oranges. `leverage_with_prices` exists and is used in the dashboard, but the raw `leverage` property is exposed and incorrect.
- **Impact:** Low — dashboard uses `leverage_with_prices`. But any external consumer of `.leverage` gets a wildly wrong number.
- **Status:** Fixed.

## 12. Hardcoded 0.44 Utilization in Multiple Locations

- **Code:** `src/simulation/monte_carlo.py:20` (`OUParams.theta=0.44`), `src/stress/shock_engine.py:129` (`0.44 + shocks`), `src/dashboard/components/sidebar.py:72` (`value=44`)
- **Issue:** All based on the wrong utilization formula from bug #1. The correct WETH utilization is `2.2M / 2.8M ≈ 0.786`, not `2.2M / (2.8M + 2.2M) ≈ 0.44`.
- **Why it matters beyond bug #1:** Even after fixing the utilization formula in `pool.py`, these hardcoded defaults push the OU process, correlated scenarios, and sidebar defaults toward 0.44, producing simulations centred on a false baseline.
- **Impact:** All simulations and correlated scenarios use a mean utilization that's ~half the correct value.
- **Status:** Fixed.

## 13. Liquidation Probability Chart Broken After MC Rewrite

- **Code:** `src/dashboard/components/charts.py:252-303`
- **Issue:** The cumulative liquidation chart used `np.minimum.accumulate(mc_result.pnl_paths)` to detect when each path was first "liquidated." After the MC rewrite (bug #4), P&L = equity − initial_equity, which is typically monotonically decreasing when borrow rates exceed income. So the cumulative min of P&L equals the P&L itself at each step, and the condition `cum_min_pnl[:, t] <= cum_min_pnl[:, -1]` only becomes true at the final timestep.
- **Why it is wrong:** The chart showed all liquidation events occurring on the very last day, regardless of when HF actually dropped below 1.0. The P&L-based proxy was designed for the old model where P&L directly drove liquidation detection. After the rewrite, liquidation is detected via HF = (collateral × threshold) / debt < 1.0, but `hf_paths` was not stored in `MonteCarloResult`, so the chart had no way to reconstruct the actual timing.
- **Impact:** The "Cumulative Liquidation Probability" chart was visually meaningless — it appeared as a flat line that jumped to the final probability on the last day.
- **Fix:** Added `hf_paths` to `MonteCarloResult`. Chart now uses `np.minimum.accumulate(mc_result.hf_paths)` and checks `cum_min_hf < 1.0` at each step, accurately showing when each path first breaches the liquidation threshold.
- **Status:** Fixed.

## 14. Historical Scenario P&L Ignores Borrow Cost and Utilization Shock

- **Code:** `src/stress/shock_engine.py:68-72`, `src/dashboard/tabs/stress_tests.py:48-75`
- **Issue:** `apply_scenario` computes `pnl_impact = collateral_after - collateral_before`, capturing only the instantaneous collateral change from the peg shock. The `utilization_shock` and `duration_days` fields on `StressScenario` are defined and displayed in the scenario table but have no effect on P&L or HF.
- **Why it is wrong:** During the June 2022 scenario, utilization spiked to 0.95 (above the 0.92 kink), pushing the borrow rate to ~17.7%. Over 14 days, this costs `10,500 × 0.177 × 14/365 ≈ 71 ETH` in borrow interest — a non-trivial amount that was completely omitted. The displayed "P&L Impact" understated the actual loss.
- **Impact:** Historical and custom scenarios showed misleadingly small losses. The utilization and duration columns in the table were decorative — they had no effect on any computed metric.
- **Fix:** The dashboard now computes the full period P&L: `peg_P&L + staking_income − borrow_cost`, where `borrow_cost = debt × stressed_borrow_rate(utilization_shock) × duration/365`. Both historical and custom scenario displays now reflect the complete P&L including borrow costs.
- **Status:** Fixed.

## 15. Correlated VaR Liquidation Check Mixes P&L into Collateral

- **Code:** `src/stress/var.py:89-92`, `src/dashboard/tabs/stress_tests.py:246-252`
- **Issue:** `compute_var_from_scenarios` computed liquidation as `HF = ((collateral + pnl) × threshold) / debt`. The `pnl` includes both collateral-side changes (peg) *and* debt-side costs (borrow rate). Adding borrow cost to the collateral side rather than the debt side gives incorrect HF values.
- **Why it is wrong:** HF = (stressed_collateral × threshold) / stressed_debt. Borrow cost increases debt, it does not decrease collateral. The previous formula was `((coll + coll_change + income − borrow_cost) × threshold) / debt`, but correct is `((coll + coll_change + income) × threshold) / (debt + borrow_cost)`. For positive-equity positions, the old formula overestimated HF, underestimating liquidation probability.
- **Impact:** The correlated VaR's liquidation probability was slightly optimistic. For borderline cases near HF = 1.0, this could be the difference between reporting "safe" and "liquidatable."
- **Fix:** `compute_var_from_scenarios` now accepts optional `stressed_collateral_array` and `stressed_debt_array` for proper per-scenario HF computation. The correlated scenario loop in the dashboard now tracks stressed collateral and debt separately and passes both arrays. Backward compatible — falls back to the old method if arrays are not provided.
- **Status:** Fixed.

---

Fixing all fifteen items is necessary before the dashboard can be considered a faithful reproduction of the Aave pool and the Mellow vault strategy.
