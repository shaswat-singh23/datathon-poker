# agent.py's time accounting now tracks the judge's charge (grace credited)
- Issue: #46 | Author: Kyle (Claude Code) | Time: 16:22
- Claim: agent.py's `memory["_spent"]` now runs **3-8% above** the judge-style charge over a 1000-deal match (it was 63-99% above at the 8 s bank and 4-7x at the 4 s bank), and never below it in any half measured. With that time handed to Monte Carlo, the field result goes **24.5 → 26.0 / 36 at `--time-bank 4`** (+2.968 → +3.268 bb/deal) and **26.0 → 26.5 / 36 at `--time-bank 8`** (+3.200 → +3.259 bb/deal; 25.5 / +3.260 in a repeat on the rebased commit, i.e. unchanged within noise), with 0 errors, 0 forfeits and 0 empty banks in 144 hero halves.
- Evidence: paired runs of master `3868baf` (exported with `git archive`) and this branch, one after the other on the same 10-core laptop, `--procs 3`. Commands and tables below.
- So what: `bot/timing.py` budgets against agent.py's number, so the phantom ~1 ms per decision left a third of the real 8 s bank, and most of the 4 s test bank, unused. Now nearly the whole budgeted bank goes to equity estimates, and the 4 s test bank plays like the 8 s one (26.0 vs 26.5 points).
- Checked by: unchecked

## The change
The judge charges each request `max(0, elapsed - 1 ms)` (`game.NETWORK_GRACE_SECONDS`), where `elapsed` includes HTTP/JSON overhead our timer can't see; `on_hand_end()` runs inside the same `/act` request as `choose_action()`. agent.py charged every decision `real time + 0.5 ms` and every `on_hand_end` its real time, with no grace.

Now each decision is charged `max(0, hand_end + real time + 0.5 ms - 0.9 ms)`, where `hand_end` is the `on_hand_end()` time of the same request (already charged when it ran, re-charged here under the shared grace). Net: our time minus 0.4 ms, floored at 0.

Safety: this is at or above the judge's charge whenever the request overhead the judge sees beyond our timer is at most 0.6 ms (measured with judge_engine against local uvicorn: 0.18-0.4 ms; `tools/sim.py` models 0.5 ms). If a slow tournament network ate the whole 1 ms grace, we would under-count by at most 0.4 ms per decision, about 1.2 s per half at ~3000 decisions, which is inside timing.py's 1.5 s reserve at the real 8 s bank, and agent.py's 0.25 s emergency cutoff is still there behind it.

`bot/timing.py`: `WRAPPER_OVERHEAD_MS` 0.5 → 0.0 (a cheap decision now costs nothing) and the docstring note. `tests/test_timing.py`: the simulated half charges the way agent.py now does; the two "fixed cost alone exceeds the bank" tests get an explicit non-MC cost that still exceeds the bank under the new accounting.

## Spent vs charged (Done-when 1)
One 1000-deal match (2 halves) in-process, `memory["_spent"]` at the end of each half vs the sim's judge-style `think_s` for that half (0.5 ms overhead, 1 ms grace). Probe script: a subclass of `tools/sim.py`'s `InProcessAgent` that reads the hero's memory after `judge_engine.play_half`. Load 8-12.

| opponent | bank | master spent / charged (2 halves) | ratio | branch spent / charged | ratio |
|---|---|---|---|---|---|
| tag | 4 s | 6.37 / 1.57 s | 4.07 | 5.99 / 5.65 s | 1.059 |
| potodds | 4 s | 6.57 / 1.11 s | 5.93 | 6.00 / 5.61 s | 1.070 |
| calling_station | 4 s | 6.43 / 0.91 s | 7.09 | 5.99 / 5.55 s | 1.079 |
| tag | 8 s | 12.57 / 7.69 s | 1.63 | 11.54 / 11.20 s | 1.030 |
| potodds | 8 s | 12.64 / 6.38 s | 1.98 | 11.87 / 11.41 s | 1.040 |
| calling_station | 8 s | 12.67 / 6.38 s | 1.99 | 11.74 / 11.26 s | 1.042 |

Every half had spent ≥ charged on the branch (smallest per-half margin: 0.16 s). Gap per half: master 2.4-3.1 s, branch 0.16-0.24 s.

Grace credit sweep (vs tag, same probe, `_spent / think` over 2 halves; a first sweep without the hand-end folding gave 1.18/1.09 at 0.75 ms):

| grace credit | 0 (master) | 0.5 ms | 0.75 ms | 0.85 ms | **0.9 ms** | 1.0 ms |
|---|---|---|---|---|---|---|
| 4 s bank | 4.46 | 1.48 | 1.18 | 1.10 | **1.06** | 0.99 (below the judge) |
| 8 s bank | 1.67 | 1.20 | 1.09 | 1.05 | **1.03** | 1.00 (below the judge) |

0.9 ms is the largest credit that stays within 10% at the 4 s bank with margin and above the judge in the sim; 1.0 ms dips under (the judge also charges `new_half` and the final hand-result flush, which agent.py doesn't see).

## Field (Done-when 2)
```
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank {4,8} --procs 3 --json <scratch>/46-{base,new}-tb{4,8}.json
```
| run | points | bb/deal | errors | empty banks | max half think | max call | load (1-min, start → end) |
|---|---|---|---|---|---|---|---|
| master, 4 s | 24.5 / 36 | +2.968 | 0 | 0 | 2.33 s | 124.4 ms | 14.0 → 36.1 |
| branch, 4 s | **26.0 / 36** | **+3.268** | 0 | 0 | 2.91 s | 55.8 ms | 36.1 → 12.3 |
| master, 8 s | 26.0 / 36 | +3.200 | 0 | 0 | 4.84 s | 212.1 ms | 12.3 → 12.4 |
| branch, 8 s | **26.5 / 36** | **+3.259** | 0 | 0 | 5.96 s | 278.1 ms | 12.4 → 12.1 |

Per opponent at 4 s, the moves are potodds (-0.333 → +1.293, 1.0 → 3.0 points; note potodds emptied its own bank in 3 master halves), lag +0.89, always_half +0.62, tag +0.16; nothing lost more than 0.1 bb/deal. At 8 s every row is within ±0.6 bb/deal (noise level per #35), trappy picked up a win (1.5 → 2.0).

Max half think stays under the bank (2.91 of 4 s, 5.96 of 8 s; timing.py's design ceiling is bank minus reserve: 3.25 / 6.5 s). The sim prints "near bank limit" for the branch at 8 s because raw compute (7.38 s, before the per-request grace) is over 75% of 8 s; the judge charges the 5.96 s.

**Decisions over 100 ms.** Wall-clock spikes appear in both runs at load 12-36: 8 hero halves over 100 ms on master at 8 s, 4 on the branch (3 of them the potodds seeds, which ran concurrently), 1 on master at 4 s, 0 on the branch at 4 s. The change does not raise any per-decision cap (timing.py's CEIL_MS is still 12 ms). A rerun of agent vs potodds (`tools/sim.py agent.py tools/opponents/potodds.py --seeds 3 --procs 3 --time-bank 8`) at load 9.6 → 8.7 gave max call **16.7 ms**, 0 errors, max half think 5.75 s. So these are OS pauses on a loaded box, not bot code.

### Repeat on the rebased commit (master `bb7fb8f`, sim with CPU-time columns from #60)
Master gained `bot/exploit.py` (not wired into `bot/policy.py` yet) and the sim's CPU-time columns; bot behaviour is unchanged. Same command, this branch only:

| run | points | bb/deal | errors / forfeits / empty banks / skipped | max half think | max call wall / **CPU** | load (start → end) |
|---|---|---|---|---|---|---|
| branch, 4 s | 27.0 / 36 | +3.193 | 0 / 0 / 0 / 0 | 2.99 s | 193.8 / **13.2 ms** | 9.4 → 36.7 |
| branch, 8 s | 25.5 / 36 | +3.260 | 0 / 0 / 0 / 0 | 5.89 s | 153.8 / **14.5 ms** | 36.7 → 10.6 |

So the field result at 8 s is 25.5-26.5 for the branch vs 26.0 for master (same bb/deal, +3.26 vs +3.20): no change beyond noise at the real bank; at 4 s it is 26.0-27.0 vs 24.5. No decision used more than 14.5 ms of CPU; the 5 wall-clock spikes over 100 ms per run are OS pauses at load up to 57.

## Checks
- `python -m pytest -q`: 459 passed on the rebased commit (one run during a load-57 burst failed `test_postflop.py::test_huge_budget_is_capped_and_fast` on wall time, 150 ms; it passes on rerun and this branch does not touch postflop).
- `./tools/check_build.sh`: ALL CHECKS PASSED on the rebased commit.
- Rule 3: the gain is where the change says it should be (bots that the hero needs equity against, mostly at 4 s where the phantom charge was biggest), and the 8 s change is within noise. Nothing looks too good.
