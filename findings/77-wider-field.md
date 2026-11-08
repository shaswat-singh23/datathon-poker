# Wider sparring field: the hero beats or chops fit-or-fold, always-cbet and honest-equity bots at both banks
- Issue: #77 | Author: Shaswat (agent) | Time: 18:22
- Claim: Three new sparring bots (`fitorfold`, `cbetter`, `honest`) do **not** expose a gap in master. The hero wins 3-0 against `honest` and `fitorfold` and chops `cbetter` (CI spans 0), at the real 8 s bank and at 4 s: **7.5 / 9 points at both**. An earlier version of this file claimed `fitorfold` beat us 0-3 (-1.313 bb/deal); that did **not** reproduce (+1.059 now, reviewer got +0.791) and is withdrawn.
- Evidence: `python tools/sim.py --hero agent.py --field tools/opponents/fitorfold.py tools/opponents/cbetter.py tools/opponents/honest.py --seeds 3 --time-bank {8,4} --procs 4 --quiet` (3 seeds x 1000 deals, duplicate format), master `49eee6d` (includes #69 exploit wiring and #70) plus this PR's bots. Each run started at 1-minute load 0.7 to 3.9 (gate: below nproc/2 = 8) with no other sweep running (`uptime` checked before each).

| opponent | 8 s bb/deal [95% CI] | pts | 4 s bb/deal [95% CI] | pts |
|---|---|---|---|---|
| honest | +2.714 [+2.263, +3.165] | 3.0 | +2.601 [+2.138, +3.064] | 3.0 |
| fitorfold | +1.059 [+0.747, +1.370] | 3.0 | +0.921 [+0.618, +1.223] | 3.0 |
| cbetter | -0.145 [-0.734, +0.444] | 1.5 | -0.230 [-0.806, +0.347] | 1.5 |
| total | +1.209 | 7.5 / 9 | +1.097 | 7.5 / 9 |

- **The bots' own results vs the existing field** (`baseline-bots/*.py` + the 8 older `tools/opponents/*.py`, 12 opponents). `python tools/sim.py --hero tools/opponents/<bot>.py --field tools/opponents/{exploiter,lag,maniac,nit,potodds,rock_shover,tag,trappy}.py baseline-bots/*.py --seeds 3 --time-bank 8 --procs 4`. Cells are bb/deal ±95% CI half-width (points of 3.0 over 3 seeds):

| opponent | fitorfold | cbetter | honest |
|---|---|---|---|
| baseline_always_half | +0.65 ±1.01 (1.5) | +1.34 ±0.98 (2.5) | +12.10 ±0.81 (3.0) |
| baseline_always_pot | +4.68 ±0.90 (3.0) | +2.59 ±1.05 (3.0) | +7.07 ±0.94 (3.0) |
| baseline_calling_station | +7.73 ±0.48 (3.0) | +1.88 ±0.47 (3.0) | +8.03 ±0.43 (3.0) |
| baseline_random | +4.37 ±0.67 (3.0) | +5.55 ±0.81 (3.0) | +9.20 ±0.80 (3.0) |
| exploiter | -0.41 ±0.33 (1.0) | +0.59 ±0.62 (1.5) | -2.73 ±0.48 (0.0) |
| lag | +3.89 ±0.67 (3.0) | +1.42 ±0.73 (2.5) | +4.78 ±0.60 (3.0) |
| maniac | +4.92 ±0.90 (3.0) | +1.81 ±1.06 (2.5) | +8.54 ±0.90 (3.0) |
| nit | +0.03 ±0.27 (1.5) | +1.31 ±0.34 (3.0) | -1.33 ±0.39 (0.0) |
| potodds | +2.29 ±0.44 (3.0) | +0.10 ±0.51 (1.5) | -0.93 ±0.38 (0.0) |
| rock_shover | +0.53 ±0.27 (2.5) | +0.63 ±0.40 (2.5) | +0.57 ±0.43 (1.5) |
| tag | -0.11 ±0.31 (1.5) | +1.00 ±0.53 (2.5) | -3.28 ±0.46 (0.0) |
| trappy | +0.25 ±0.32 (1.5) | -1.64 ±0.45 (0.0) | -1.64 ±0.40 (0.0) |
| **points (W-L-C)** | **27.5 / 36** (20-1-15), mean +2.402 | **27.5 / 36** (22-3-11), mean +1.382 | **19.5 / 36** (18-15-3), mean +3.366 |

  `fitorfold` and `cbetter` are solid mid-field bots (neither loses to anything except `exploiter` and `trappy` respectively); `honest` crushes the always-raise baselines but loses 0-3 to `tag`, `exploiter`, `trappy`, `nit`, `potodds`, so it is the weakest of the three. Each bot mostly beats the baselines and chops or loses to the better sparring bots, which is the ordering we want from stand-in student bots.
- Done-when checks: 0 errors and 0 forfeits in every one of the 126 matches above. Max wall per decision: new bots 46.6 ms (`cbetter` vs `lag`; `fitorfold` 20.1, `honest` 17.1), hero 13.0 ms (CPU 12.8 ms); all under 100 ms. `python -m pytest -q`: 465 passed. `./tools/check_build.sh` could not run in this session (no Docker in this WSL); the PR touches only `tools/opponents/` and `findings/`, so the image content is identical to master, and `tools/smoke_test.py` against a local `agent.py` server passed. The reviewer's Docker run is the check of record.
- Bot fix in this PR: the first version of the bots started cutting Monte Carlo samples only after spending 4.0 s, so at the 4 s test bank `honest` emptied its bank in all 6 halves (think 4.0 s of 4.0 s, per the reviewer) and played check/fold for the rest, i.e. was not a real opponent at 4 s. All three now pace the Monte Carlo spend evenly over the half (budget `min(4.0, 0.5 x bank)` seconds, scaled by hand index), because the sim also charges ~0.5 ms per call (~1.6 s per half). At 4 s their longest half is now 1.6 s (`fitorfold`), 1.8 s (`cbetter`), 2.5 s (`honest`) of 4 s, with no bank-empty. At 8 s the budget is still 4.0 s, only paced rather than front-loaded.
- Caveats:
  1. Why the old run lost: not established. The old file's hero showed CPU max 144-285 ms per decision (vs 10-13 ms now) while two other sweeps were running, so the hero was probably time-starved (its budgets come from the wall clock); the run also lacked #69's exploit wiring. Neither cause was tested. The old diagnosis (`tools/analyze.py` on that run) is dropped with it.
  2. The sim flags the hero as "near bank limit" at 8 s (max half think 5.93 s of 8 s). That is hero timing policy, outside this ticket; it is a margin, not an error.
  3. These are my guesses at student styles, not data on the real field. `cbetter` is the one style where we only chop (-0.145 [-0.734, +0.444]); that would be the place to look for the extra half point per match.
- So what: the three styles most likely to appear in a student field do not beat the current bot, so no new gap comes from this experiment. A judge should read it as a negative result: the edge generalizes to fit-or-fold, always-cbet and honest-equity opponents at both banks.
- Checked by: unchecked
