# bot/timing.py grants Monte Carlo to every postflop decision at the 4 s test bank
- Issue: #35 | Author: Kyle (Claude Code) | Time: 15:30
- Claim: at `--time-bank 4`, `bot/timing.py` now grants **100% of postflop decisions** a budget above postflop's Monte Carlo minimum (0.31 ms), in both halves of a 1000-deal match vs tag, median budget 0.9 ms. On the starting commit it was 25% / 19%, and 0% for the first 40% of the half. The field result at 4 s goes from **18.0 / 36** (#38, same starting commit) to **22.0 / 36** (+1.256 → +2.245 bb/deal), and a paired rerun under the same load repeats it: 17.5 for the starting commit, 22.0 for this branch. At the real 8 s bank nothing is lost: a paired rerun under the same load gives 25.5 / 36 for the starting commit and 26.0 / 36 for this branch. 0 errors, forfeits or bank empties in 288 hero halves. The bot's own CPU per decision stays under 15 ms; wall-time spikes over 100 ms in the sim are OS pauses on a box at load 35-127.
- Evidence:
  - Starting commit `0256393432ee0eec83b88978cfc12f9e4b3a6877` (master). Code at `95460b2` (the `bot/timing.py` commit of this branch, rebased onto master `d52b2fa`; master gained only tool changes, #44 and #45, between the two). Machine: 10-core Mac; 1-min load average 34-127 throughout, from other sessions' sims. Wall-clock numbers (what agent.py and the judge charge) are therefore inflated and noisy, so CPU time per call is reported where it matters.
  - Why it was starved (the issue's diagnosis, confirmed by reading `budget_ms`): at hand 0 of a 4 s half the old code held back a flat 1.5 s reserve plus an overhead allowance of 1000 hands × 3.0 decisions × 0.65 ms × 1.25 = 2.44 s, leaving 0.06 s, i.e. 0.2 ms budgets, below postflop's 0.31 ms minimum. Two further leaks: the spendable time was spread over *every* expected decision although only postflop ones call `budget_ms` (preflop is a table lookup, ~38% of decisions), so the plan under-spent and budgets only recovered late in the half; and 0.2 ms budgets were granted but never used.
  - What changed (`bot/timing.py` only; `bot/policy.py`, `bot/postflop.py` untouched):

    | | before | after | why |
    |---|---|---|---|
    | reserve | 1.5 s flat | 12.5% of the bank, min 0.4 s (1.0 s of 8 s, 0.5 s of 4 s) | a flat 1.5 s is 37% of the 4 s test bank; agent.py's own emergency stop is at 0.25 s |
    | split of spendable time | over all expected decisions | over expected *budget requests* (postflop), measured as `_tb_calls / _decisions` after 20 hands, prior 0.7, floor 0.2 | preflop never asks |
    | FLOOR_MS | 0.2 | 0.4 | any non-zero grant now clears postflop's 0.31 ms minimum; the equity engine runs its 64-sample floor below ~0.3 ms anyway |
    | CEIL_MS | 40 | 25 | postflop hands at most 20 ms (0.8 × 25) to the equity engine; more is wasted and widens #28's overrun |
    | OVERHEAD_MARGIN | 1.25 | 1.1 | the overhead is re-measured every decision from `_spent − granted`; the reserve covers drift |

  - Budgets in a real sim match (scratch probe: wraps `choose_action` in `tools/sim.py`'s in-process agent and reads the grant from `memory["_tb_granted_s"]` before/after each call; agent.py vs `tools/opponents/tag.py`, seed `sim-0`, 1000 deals, both halves; each run alone, load 35-55):

    | bank | code | half | postflop decisions | % with budget ≥ 0.31 ms | by tenth of the half | budget p10 / p50 / p90 (ms) | agent.py `_spent` | judge-style charge | raw compute | max call wall / CPU |
    |---|---|---|---|---|---|---|---|---|---|---|
    | 4 s | before | 1 | 1845 | 25.2% | 0 0 0 0 3 17 35 63 86 73 | 0.20 / 0.20 / 0.43 | 2.49 s | 0.68 s | 1.04 s | 19.8 ms / – |
    | 4 s | before | 2 | 1593 | 18.7% | 0 0 0 3 6 25 46 43 80 100 | 0.20 / 0.20 / 0.43 | 2.37 s | 0.84 s | 1.12 s | 60.7 ms / – |
    | 4 s | after | 1 | 1883 | **100%** | 100 in every tenth | 0.51 / 0.87 / 1.86 | 3.44 s | 0.99 s | 1.95 s | 7.9 / 4.0 ms |
    | 4 s | after | 2 | 1872 | **100%** | 100 in every tenth | 0.55 / 0.94 / 2.19 | 3.43 s | 0.99 s | 1.94 s | 4.6 / 4.5 ms |
    | 8 s | after | 1 | 1898 | **100%** | 100 in every tenth | 1.13 / 1.87 / 3.29 | 6.93 s | 4.47 s | 5.45 s | 89.9 / 9.8 ms |
    | 8 s | after | 2 | 1883 | **100%** | 100 in every tenth | 1.27 / 1.98 / 3.37 | 6.96 s | 4.51 s | 5.48 s | 50.9 / 12.3 ms |

    The agent-side spend lands within 0.07 s of bank − reserve in every half: the planner does what it says. Non-Monte-Carlo decisions cost 0.02-0.03 ms of CPU; Monte Carlo decisions cost 1.0 ms (4 s) and 2.6-2.8 ms (8 s) against median grants of 0.9 and 1.9 ms, which is #28's overrun (postflop hands 80% of the grant to `equity()`, and it takes about 1.4× that). The planner measures that overrun as overhead and plans around it.
  - Field, 3 seeds × 1000 deals, duplicate format, same field and seed base as #9 and #38, `--procs 5`, in the background with logs:

    ```
    .venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 4 --procs 5 --json data/35-field-tb4.json
    .venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 8 --procs 5 --json data/35-field-tb8.json
    ```

    "Before" is #38's run of the starting commit `0256393` (`findings/37-field-om.md`, PR #42); #9's numbers (`findings/9-field.md`, 17.5 and 25.0 points) are the same within noise. The 8 s "before" and "after" columns are a paired rerun: the starting commit (run from the master checkout) and this branch, one after the other, same flags, load 46-68. The first 8 s run of this branch (`data/35-field-tb8.json`) landed at 23.0 / 36 (+2.401) because it ran while the box was at load 127 and overlapped my CPU probe; it is kept as the noise reference below.

    | opponent | before, 4 s (#38) | pts | after, 4 s | pts | Δ bb/deal | before, 8 s (paired) | pts | after, 8 s (paired) | pts | Δ bb/deal |
    |---|---|---|---|---|---|---|---|---|---|---|
    | baseline_calling_station | +7.862 [+7.366, +8.357] | 3.0 | +8.103 [+7.592, +8.613] | 3.0 | +0.24 | +8.909 [+8.387, +9.431] | 3.0 | +8.948 [+8.425, +9.470] | 3.0 | +0.04 |
    | baseline_always_half | +6.953 [+6.163, +7.743] | 3.0 | +7.196 [+6.382, +8.011] | 3.0 | +0.24 | +8.940 [+8.080, +9.799] | 3.0 | +9.266 [+8.416, +10.115] | 3.0 | +0.33 |
    | baseline_random | +5.647 [+4.800, +6.495] | 3.0 | +5.362 [+4.529, +6.196] | 3.0 | −0.29 | +5.560 [+4.814, +6.305] | 3.0 | +5.725 [+4.970, +6.480] | 3.0 | +0.17 |
    | baseline_always_pot | +3.550 [+2.592, +4.508] | 3.0 | +4.519 [+3.548, +5.490] | 3.0 | +0.97 | +5.842 [+4.878, +6.806] | 3.0 | +6.058 [+5.095, +7.021] | 3.0 | +0.22 |
    | maniac | +3.477 [+2.534, +4.420] | 3.0 | +5.768 [+4.801, +6.735] | 3.0 | **+2.29** | +6.563 [+5.608, +7.518] | 3.0 | +6.472 [+5.515, +7.430] | 3.0 | −0.09 |
    | rock_shover | +0.794 [+0.402, +1.186] | 2.5 | +0.717 [+0.330, +1.103] | 2.5 | −0.08 | +0.750 [+0.382, +1.117] | 2.5 | +0.754 [+0.385, +1.123] | 2.5 | +0.00 |
    | trappy | −0.910 [−1.243, −0.578] | 0.0 | −0.141 [−0.392, +0.111] | 1.5 | **+0.77** | +0.294 [+0.030, +0.559] | 1.5 | +0.232 [−0.029, +0.494] | 1.5 | −0.06 |
    | nit | −1.046 [−1.400, −0.692] | 0.0 | −0.402 [−0.724, −0.079] | 1.0 | **+0.64** | −0.390 [−0.702, −0.077] | 1.0 | −0.414 [−0.730, −0.098] | 1.0 | −0.02 |
    | lag | −1.198 [−1.784, −0.612] | 0.5 | +1.101 [+0.478, +1.724] | 2.0 | **+2.30** | +3.871 [+3.288, +4.455] | 3.0 | +3.905 [+3.312, +4.498] | 3.0 | +0.03 |
    | potodds | −1.986 [−2.384, −1.589] | 0.0 | −1.276 [−1.673, −0.879] | 0.0 | +0.71 | +0.826 [+0.431, +1.221] | 2.5 | +1.148 [+0.747, +1.550] | 3.0 | +0.32 |
    | tag | −3.810 [−4.313, −3.306] | 0.0 | −2.118 [−2.552, −1.685] | 0.0 | **+1.69** | −1.638 [−2.040, −1.236] | 0.0 | −1.714 [−2.122, −1.306] | 0.0 | −0.08 |
    | exploiter | −4.264 [−4.846, −3.681] | 0.0 | −1.889 [−2.346, −1.431] | 0.0 | **+2.38** | −1.402 [−1.835, −0.969] | 0.0 | −1.523 [−1.963, −1.083] | 0.0 | −0.12 |
    | **total** | mean +1.256 [+1.067, +1.444] | **18.0** | mean +2.245 [+2.060, +2.430] | **22.0** | +0.99 | mean +3.177 [+2.995, +3.359] | **25.5** | mean +3.238 [+3.055, +3.421] | **26.0** | +0.06 |

    Paired 4 s rerun (starting commit from the master checkout, then this branch, same flags, load 60-82; `data/35-field-tb4-rerun.json`): **17.5 / 36** (+1.205 [+1.014, +1.396]) → **22.0 / 36** (+2.322 [+2.136, +2.508]). Same rows move: maniac +4.04 → +6.59, lag −1.40 → +0.77 (0 → 2.0 pts), trappy −0.96 → −0.10 (0 → 1.5), nit −0.81 → −0.45 (0 → 1.0), tag −3.78 → −2.87, exploiter −4.25 → −2.18, potodds −3.93 → −2.60, always_pot +4.23 → +5.77. 0 errors / forfeits / bank empties in either run.

    Safety, hero, all 72 halves of each run:

    | | before, 4 s (paired) | after, 4 s | after, 4 s (paired) | before, 8 s (paired) | after, 8 s (paired) | after, 8 s (first run, load 127) |
    |---|---|---|---|---|---|---|
    | errors / forfeits / bank emptied | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
    | max charged think time per half | 1.57 s (limit 4 s) | 2.67 s (limit 4 s) | 2.51 s (limit 4 s) | 5.09 s (limit 8 s) | 5.83 s (limit 8 s) | 6.35 s (limit 8 s) |
    | max raw compute per half | 1.82 s | 2.92 s | 2.78 s | 5.50 s | 6.13 s | 6.62 s |
    | mean charged think per half | 0.66 s | 1.64 s | 1.33 s | 3.94 s | 4.50 s | 4.88 s |
    | mean per decision | 0.33 ms | 0.76 ms | 0.67 ms | 1.63 ms | 1.83 ms | 1.85 ms |
    | max single decision (wall) | 294.5 ms | 175.4 ms | 442.1 ms | 196.6 ms | 214.3 ms | 655.9 ms |
    | halves with a wall-time decision over 100 ms | 6 | 23 | 10 | 15 | 10 | 62 |
    | opponent halves that emptied their own bank | 8 of 72 | 18 of 72 | 6 of 72 | 0 | 0 | 5 |

    For reference, #38 saw 1.70 s max think, 94.2 ms max call and 0 halves over 100 ms at 4 s on the starting commit, at load 2-18. The wall-time spikes here hit the starting commit too (294.5 ms and 6 halves in its paired 4 s run, 15 halves at 8 s) and the trivial baseline bots as much as the thinking ones, which is the signature of CPU contention, not of a code path.
  - CPU time of every hero decision, whole field at 4 s (second scratch probe, one process, seed `sim-0`, 12 opponents × 2 halves = 58,165 calls, `time.thread_time` per call plus a gen-2 GC flag, load 60-127): worst CPU for the bot's own work **14.4 ms** (trappy, a 5.7 ms grant on the turn). One call used 78.3 ms of CPU: a gen-2 garbage collection inside the long-lived probe process after 20 earlier halves, the same effect #13 measured (3.9 ms for a full GC in a fresh process, which is what the judge runs). 31 calls were over 100 ms of wall time, with 0.1-12 ms of CPU each; 0 calls were over 100 ms of CPU.
- Sanity (Rule 3): the gain is where the issue said it would be, and only there. At 4 s the rows that moved are the ones that need equity to play against (maniac +2.3, lag +2.3, exploiter +2.4, tag +1.7, always_pot +1.0, trappy, nit, potodds +0.6 to +0.8); the deterministic calling_station/always_half rows moved +0.24 (they are hit by the budgets too, as timing is wall-clock), and the 4 s result (22.0, +2.245) is still below the 8 s one (26.0, +3.238), as it should be with agent.py's accounting leaving less real time at 4 s. At 8 s, where Monte Carlo already ran on nearly every postflop decision, nothing moved past #38's same-commit noise (0.5 points, 0.14 bb/deal in the mean, up to 0.65 against one opponent): +0.5 points, +0.06 bb/deal, largest row +0.33. Fewer opponent halves emptied their own bank in the new 4 s run (18 vs 27-28 in #38's runs), so load helped this run *less* than the baseline runs, not more. Nothing looks too good.
- Caveats:
  1. The binding constraint at 4 s is agent.py's accounting, not the judge's. agent.py charges real time + 0.5 ms per decision and ignores the judge's 1 ms grace, so its `_time_left` runs about 1 ms per decision (2.5-3 s per half) below what the judge really charges: 3.44 s vs 0.99 s in the probe above. Since agent.py stops calling the policy when *its* number drops under 0.25 s, timing.py must plan against it, and roughly a third of the real bank stays unused. Filed as #46 (agent.py is outside this ticket's scope).
  2. Wall-clock timing on a box at load 35-127 is noisy. The first 8 s run of this branch (23.0 points) vs the paired rerun (26.0) shows how much: 3 points from load alone. Read per-opponent moves under 0.65 bb/deal as noise, and rerun paired when a claim is close.
  3. More decisions now run Monte Carlo at 8 s, so #28's 1.4× overrun shows up on more calls; CEIL_MS 25 bounds it to about 20 × 1.4 ≈ 30 ms of CPU per call. The 100 ms wall-time spikes under load are the OS, not the bot (CPU ≤ 14.4 ms in 58k calls).
- So what: the test bank finally tests the strategy, not the budget manager. The 4 s run was 17.5-18.0 points because Monte Carlo was off for most of each half; now it is 22.0 and every postflop decision gets an equity estimate at both banks. Tickets tuning postflop/preflop against the field (#39, #12) can use `--time-bank 4` and see the same decision logic the tournament will run. The remaining gap between the 4 s and 8 s results is agent.py's phantom charge (#46), not timing.py.
- Checked by: unchecked
