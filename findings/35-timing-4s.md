# bot/timing.py grants Monte Carlo at the 4 s test bank
- Issue: #35 | Author: Kyle (Claude Code) | Time: 15:30
- Claim: at `--time-bank 4`, every postflop decision now gets a Monte Carlo budget above postflop's minimum (100% vs tag, 99.8% vs the calling station, in a 1000-deal half; master: 7–21%, and nothing before hand 348). Charged time per half stays under 2.4 s of 4 s, 0 errors. Points on the 12-bot field rise at 4 s (paired runs on the same machine: 20.0 → 23.0 with 8 workers, 20.5 → 21.5 with 3 workers, every opponent's bb/deal up) and are unchanged at 8 s (26.0 → 26.0 with 3 workers).
- Evidence: commands below, master = `0256393432ee0eec83b88978cfc12f9e4b3a6877`, this branch = the `#35: timing` commit (PR #35's branch) + this file. 10-core Apple Silicon laptop, `timing.calibrate()` reports 1.36× slower than the reference machine. Sim JSON in `data/35-*.json` (local).

## What was wrong
`bot/timing.py` computes a per-decision budget from `memory["_time_left"]` (agent.py's accounting: real time + 0.5 ms per decision). At hand 0 of a 4 s half it held back a flat 1.5 s reserve plus an overhead allowance of 1000 hands × max(dph, 3.0) × 0.65 ms × 1.25 = 2.44 s, leaving 0.06 s. Budgets came out at the 0.2 ms floor, below postflop's 0.3125 ms Monte Carlo minimum (`PARAMS["min_budget_ms"] / PARAMS["budget_frac"]`), so postflop used the made-hand fallback. Three more things kept it starved: the measured overhead could only raise the allowance, never lower it; the allowance assumed at least 3 decisions per hand for the whole half even after observing fewer; and the spendable time was divided over *all* remaining decisions although preflop (about 40% of them) plays from the table and never asks for a budget, so that share was never spent.

Probe: a hero wrapper around `agent.py` that records every `budget_ms()` result, one 1000-deal match in-process at `--time-bank 4`, seed `sim-0`.

| 4 s bank, hero half | postflop decisions | share with budget > 0.3125 ms | first hand with MC | mean budget | internal spent (agent.py) | sim charged |
|---|---|---|---|---|---|---|
| master vs tag, half 1 | 1381 | 20.9% | 348 | 0.32 ms | 2.35 s | 1.02 s |
| master vs tag, half 2 | 1418 | 17.6% | 368 | 0.35 ms | 2.40 s | 1.05 s |
| master vs calling_station, half 1 | 2706 | 11.2% | 753 | 0.13 ms | 2.49 s | 0.44 s |
| master vs calling_station, half 2 | 2661 | 6.9% | 695 | 0.12 ms | 2.49 s | 0.54 s |
| **new** vs tag, half 1 | 1886 | **100%** | 0 | 0.70 ms | 3.23 s | 0.78 s |
| **new** vs tag, half 2 | 1753 | **100%** | 0 | 0.81 ms | 3.24 s | 0.92 s |
| **new** vs calling_station, half 1 | 2706 | **99.8%** | 0 | 0.42 ms | 3.24 s | 0.20 s |
| **new** vs calling_station, half 2 | 2661 | **99.8%** | 0 | 0.43 ms | 3.24 s | 0.23 s |

Max single decision in these probes: new 2.3–4.9 ms (master 40–56 ms). At 8 s vs tag, both versions grant 100%; new mean budget 2.4–2.7 ms (master 2.2–2.3 ms), max 7 ms (master 18 ms), internal spent 6.44 s of the 6.5 s target.

## What changed (bot/timing.py only)
1. **Reserve scales with the bank**: `reserve_s(bank) = max(0.5, 1.5/8 × bank)`: 1.5 s at 8 s (unchanged), 0.75 s at 4 s.
2. **After warm-up (20 hands, 50 decisions) the overhead allowance uses measurements**: the observed decisions per hand (no 3.0 floor) and the measured charge per decision beyond granted budgets (floored at the 0.5 ms agent.py always adds; margin 1.1 instead of 1.25). Monte Carlo overshooting its budget (#28) lands in that measurement, so it shrinks later budgets instead of eating the reserve. Before warm-up the old pessimistic priors apply.
3. **Spend is spread over decisions that ask for a budget**: `budget_ms` counts its own calls (`memory["_tb_calls"]`) and divides the spendable time by hands_left × dph × (calls / decisions), floored at 25%.
4. **FLOOR_MS 0.2 → 0.4**: any non-zero budget now clears postflop's 0.3125 ms minimum, so it buys samples rather than being wasted.
5. **CEIL_MS 40 → 12**: 12 ms is about 25k flop samples; more adds no precision and only exposes the #28 overrun. postflop caps what it hands to the equity engine at 20 ms anyway.

Guarantees kept (tests): 8 s worst case (8 decisions a hand) ≤ 6.5 s at 1×, 1.5×, 2× CPU; when the fixed cost alone exceeds the bank, MC adds < 0.1 s; 8 s typical half uses ≥ 5 s and spends evenly. New tests: 4 s typical half grants > 0.3125 ms to ≥ 90% of postflop decisions and stays ≤ 3.25 s; 4 s with 4 decisions a hand stays ≤ 3.25 s; 8 s with preflop never asking still uses ≥ 5 s. `python -m pytest -q`: 138 passed (after rebasing on master `7700d89`).

## Field, 4 s bank (the AGENTS.md test setting)
```
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 4 --procs 3 --json data/35-{base,new}-tb4-p3.json
```
Paired runs, master vs this branch, same seeds, one after the other, 3 workers:

| opponent | master bb/deal [95% CI] | pts | new bb/deal [95% CI] | pts | Δ |
|---|---|---|---|---|---|
| baseline_calling_station | +8.034 [+7.532, +8.536] | 3.0 | +8.511 [+7.986, +9.035] | 3.0 | +0.477 |
| baseline_always_half | +6.975 [+6.183, +7.767] | 3.0 | +7.714 [+6.900, +8.528] | 3.0 | +0.739 |
| baseline_random | +6.083 [+5.284, +6.881] | 3.0 | +6.295 [+5.529, +7.061] | 3.0 | +0.213 |
| baseline_always_pot | +4.596 [+3.644, +5.548] | 3.0 | +6.104 [+5.138, +7.069] | 3.0 | +1.508 |
| maniac | +4.454 [+3.505, +5.404] | 3.0 | +4.861 [+3.903, +5.820] | 3.0 | +0.407 |
| rock_shover | +0.732 [+0.362, +1.102] | 2.5 | +0.756 [+0.390, +1.123] | 2.5 | +0.025 |
| trappy | −0.656 [−0.956, −0.355] | 0.5 | +0.072 [−0.209, +0.354] | 1.5 | +0.728 |
| lag | −0.534 [−1.180, +0.112] | 1.5 | +0.059 [−0.581, +0.699] | 1.5 | +0.594 |
| nit | −0.604 [−0.928, −0.280] | 1.0 | −0.507 [−0.815, −0.200] | 1.0 | +0.097 |
| tag | −3.275 [−3.736, −2.814] | 0.0 | −2.790 [−3.259, −2.321] | 0.0 | +0.485 |
| exploiter | −3.782 [−4.306, −3.257] | 0.0 | −3.274 [−3.792, −2.757] | 0.0 | +0.507 |
| potodds | −4.653 [−5.170, −4.136] | 0.0 | −3.494 [−3.991, −2.997] | 0.0 | +1.159 |
| **total** | mean +1.447 | **20.5 / 36** | mean +2.026 | **21.5 / 36** | +0.578 |

Opponents kept their banks in every half of both runs except potodds, which emptied its own once (1 of 6 halves) in the new run. Every opponent's bb/deal rises; the point gain is trappy (loss → chop). The bot is still a clear loser to tag, exploiter and potodds at 4 s (that's #39's territory: strategy, not time).

The same pair with 8 workers (`--procs 8`): 20.0 → 23.0 points (+1.566 → +2.159 bb/deal), with every thinking bot improving by +0.9 to +1.4 bb/deal. With 8 workers on this 10-core laptop the opponents' own Monte Carlo ran slow and tag, exploiter, potodds, lag and trappy emptied their banks in 6 of 6 halves each (both runs), which flatters both results. The 3-worker pair is the cleaner comparison. For reference, #9's 4 s run of master on a 16-core WSL box scored 17.5 / 36 and #38's 18.0.

## Field, 8 s bank (the real bank): no regression
```
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 8 --procs 3 --json data/35-{base,new}-tb8-p3.json
```
| opponent | master bb/deal [95% CI] | pts | new bb/deal [95% CI] | pts | Δ |
|---|---|---|---|---|---|
| baseline_always_half | +9.157 [+8.300, +10.014] | 3.0 | +9.335 [+8.485, +10.185] | 3.0 | +0.178 |
| baseline_calling_station | +8.927 [+8.402, +9.452] | 3.0 | +8.977 [+8.451, +9.503] | 3.0 | +0.050 |
| maniac | +6.457 [+5.503, +7.411] | 3.0 | +6.587 [+5.627, +7.547] | 3.0 | +0.130 |
| baseline_always_pot | +5.989 [+5.020, +6.958] | 3.0 | +6.083 [+5.114, +7.052] | 3.0 | +0.094 |
| baseline_random | +5.643 [+4.895, +6.390] | 3.0 | +5.609 [+4.856, +6.362] | 3.0 | −0.034 |
| lag | +3.790 [+3.199, +4.382] | 3.0 | +3.817 [+3.219, +4.415] | 3.0 | +0.027 |
| potodds | +1.282 [+0.899, +1.665] | 3.0 | +1.146 [+0.761, +1.530] | 3.0 | −0.136 |
| rock_shover | +0.759 [+0.392, +1.125] | 2.5 | +0.747 [+0.379, +1.114] | 2.5 | −0.012 |
| trappy | +0.198 [−0.080, +0.475] | 1.5 | +0.256 [−0.005, +0.517] | 1.5 | +0.058 |
| nit | −0.412 [−0.727, −0.098] | 1.0 | −0.392 [−0.708, −0.076] | 1.0 | +0.020 |
| exploiter | −1.463 [−1.901, −1.024] | 0.0 | −1.393 [−1.813, −0.974] | 0.0 | +0.069 |
| tag | −1.786 [−2.196, −1.376] | 0.0 | −1.748 [−2.151, −1.344] | 0.0 | +0.038 |
| **total** | mean +3.212 | **26.0 / 36** | mean +3.252 | **26.0 / 36** | +0.040 |

With 8 workers the 8 s pair was 22.5 → 22.0 with per-opponent swings up to ±1.9 bb/deal in both directions (lag −1.9, potodds −1.6, exploiter −1.3, trappy +0.7). That run had 63 (master) and 51 (new) of 72 hero halves with a decision over 100 ms, so it was load noise, not strategy: the 3-worker pair above agrees to ±0.18 bb/deal on every opponent.

## Safety (hero, all 72 halves per run)
| | 4 s master, 3 w | 4 s new, 3 w | 8 s master, 3 w | 8 s new, 3 w | 4 s master, 8 w | 4 s new, 8 w |
|---|---|---|---|---|---|---|
| errors / forfeits / bank emptied | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| max charged think per half | 1.43 s | 2.38 s | 5.21 s | 5.51 s | 1.78 s | 2.63 s |
| max single decision | 56.9 ms | 142.8 ms | 434.6 ms | 188.2 ms | 158.9 ms | 645.7 ms |
| halves with a decision > 100 ms | 0 | 2 | 24 | 7 | 10 | 38 |
| mean per decision | 0.29 ms | 0.58 ms | 1.63 ms | 1.65 ms | 0.45 ms | 0.85 ms |

**Decisions over 100 ms are a measurement artefact of parallel sims on this laptop, not budgets.** Budgets never exceed 12 ms (postflop hands the engine at most 9.6 ms). Master shows the same spikes (159 ms with MC almost off at 4 s; 682 ms at 8 s), spikes drop 4–5× going from 8 to 3 workers, the 401 ms spike at 4 s was in a half against always_half with a 0.31 ms mean decision, and the in-process single-match probes peak at 4.9 ms (4 s) and 26 ms (8 s, master 93 ms). Three parallel workers still produce a 143 ms outlier once in 72 halves. A run with `--procs 1` on a quiet box is the only way to measure the bot's own maximum here; the tournament gives each bot its own CPU. The lower ceiling makes the bot less exposed to #28's overrun in any case (8 s, 3 workers: 7 halves over 100 ms vs 24 on master).

## Caveats
- agent.py's own accounting charges 0.5 ms per decision on top of real time while the judge gives 1 ms free, so the bot believes it has spent 3.2 s when the sim charges 0.2–0.9 s. That pessimism is deliberate (the real HTTP overhead is unknown) and is why the 4 s budgets are only 0.4–0.8 ms. Not changed here (agent.py is off limits for this ticket).
- At 4 s against a bot that takes every hand to showdown (3700 decisions a half) the fixed overhead alone is 2.4 s of the 3.25 s spendable, so budgets sit at the 0.4 ms floor. They still clear postflop's minimum 99.8% of the time.
- `./tools/check_build.sh`: ALL CHECKS PASSED (smoke test decisions 1–7 ms). On this Mac it needs Docker Desktop's credential helper on PATH: `PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH" ./tools/check_build.sh`.
- So what: the 4 s test setting now exercises the same code path as the real 8 s bank instead of the fallback, so 4 s results mean something, and the thinking bots lose 1 bb/deal less to us at 4 s. At 8 s nothing changes except a lower per-decision ceiling.
- Checked by: unchecked
