# Fold-equity ("pressure") betting: no gain on top of #69 / #70 (negative result, code not merged)
- Issue: #68 | Author: Kyle (Claude Code) | Time: 21:35
- Claim: on current master (#69 exploit deltas, #70 line discounts + flop stabs, #77 sparring bots, #82 cbetter gate), `bot/pressure.py` **adds nothing on points and costs points at 4 s**: **44.0 vs 44.0 / 45 at the 8 s bank** (+3.635 vs +3.605 bb/deal) and **43.5 vs 44.5 / 45 at the 4 s bank** (+3.637 vs +3.632 bb/deal). Mean bb/deal is flat (Δ +0.03 / +0.005, well inside the overall CI of ±0.16). It still gains, CI-significantly, against the folders (tag +0.42 / +0.59, nit +0.26 / +0.36, exploiter +0.51 at 8 s, fitorfold +0.37 at 4 s), but every one of those is already a 3/3 win on master, so there are no points to take. It loses, CI-significantly, against baseline_calling_station (−0.36 / −0.41), cbetter (−0.61 / −0.44, which drops cbetter from 2.5 to 2.0 points at 4 s) and lag at 4 s (−0.87), and trappy slips from 3.0 to 2.5 at 4 s. The earlier +1.5 points (26.5 → 28.0 / 36) was measured against pre-#70 master, when we were losing to tag and exploiter; #70's flop stabs and #69's exploit deltas have since taken that fold equity.
- Evidence: `tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --seed-base p68b --procs 3 --time-bank {8,4}`, 15 opponents × 3 seeds × 1000 deals, duplicate format. Branch `68-pressure` at b07b859 (origin/master a4eafee merged in) vs master `d7c334f` (a4eafee plus a findings-only commit) from a detached worktree run from its own root. Four runs back to back, same seeds, so the per-opponent Δ is paired by deal.
- So what: the code is not on master. `bot/pressure.py`, its wiring in `bot/policy.py`, `tests/test_pressure.py` and `tools/sweep_pressure.py` live only in the history of branch `68-pressure` at 4276a00; this PR merges just this findings file. The aggression the module added against folders is already in master through #70 and #69, and what remains costs value against stations, cbetter and lag. Points are the scoring metric and they are flat at 8 s and down at 4 s.
- Checked by: unchecked

## Re-measurement on current master (15 bots, seed base `p68b`)
Code measured (branch history at b07b859 / 4276a00, not on master): `bot/pressure.py` had previously recomputed equity the pre-#70 way and would have silently dropped #70's `line_discount` / `observe_aggression` scaling. The measured version applied the same discount as `bot.postflop.postflop_action`, so its only difference from master was the pressure bet itself. `tests/test_pressure.py::test_min_street_and_min_fold` compared against base postflop, since #70 flop-stabs at eq 0.35. On that commit, `python -m pytest -q`: 481 passed; `test_agent.py`: 18 passed.

Load (1-min, `sysctl vm.loadavg`), with no other sim running at any start:

| run | load before | peak | after |
|---|---|---|---|
| branch 8 s | 5.55 | 8.26 | 7.57 |
| master 8 s | 6.41 | 10.65 | 7.59 |
| branch 4 s | 7.59 | 7.59 | 5.01 |
| master 4 s | 5.01 | 5.92 | 5.90 |

N = matches per opponent (3 × 1000 deals). Δ is branch − master per deal, paired, 95% CI.

**8 s bank: master 44.0 / 45, +3.605 [+3.451, +3.759] (43-0-2); branch 44.0 / 45, +3.635 [+3.476, +3.793] (43-0-2)**

| opponent | N | master bb/deal [95% CI] | W-L-C | pts | branch bb/deal [95% CI] | W-L-C | pts | Δ [95% CI] |
|---|---|---|---|---|---|---|---|---|
| baseline_calling_station | 3 | +10.162 [+9.632, +10.691] | 3-0-0 | 3.0 | +9.803 [+9.268, +10.338] | 3-0-0 | 3.0 | -0.359 [-0.428, -0.290] |
| baseline_always_half | 3 | +8.754 [+7.891, +9.617] | 3-0-0 | 3.0 | +8.791 [+7.928, +9.653] | 3-0-0 | 3.0 | +0.037 [-0.061, +0.134] |
| baseline_random | 3 | +6.174 [+5.384, +6.965] | 3-0-0 | 3.0 | +6.142 [+5.335, +6.950] | 3-0-0 | 3.0 | -0.032 [-0.780, +0.716] |
| maniac | 3 | +5.738 [+4.754, +6.722] | 3-0-0 | 3.0 | +5.751 [+4.762, +6.740] | 3-0-0 | 3.0 | +0.013 [-0.396, +0.422] |
| baseline_always_pot | 3 | +5.566 [+4.584, +6.547] | 3-0-0 | 3.0 | +5.636 [+4.654, +6.619] | 3-0-0 | 3.0 | +0.070 [-0.102, +0.243] |
| lag | 3 | +4.301 [+3.682, +4.919] | 3-0-0 | 3.0 | +4.564 [+3.926, +5.203] | 3-0-0 | 3.0 | +0.264 [-0.273, +0.800] |
| potodds | 3 | +3.406 [+2.921, +3.892] | 3-0-0 | 3.0 | +3.395 [+2.893, +3.898] | 3-0-0 | 3.0 | -0.011 [-0.324, +0.302] |
| honest | 3 | +3.060 [+2.586, +3.533] | 3-0-0 | 3.0 | +2.818 [+2.337, +3.299] | 3-0-0 | 3.0 | -0.242 [-0.606, +0.122] |
| exploiter | 3 | +1.268 [+0.901, +1.636] | 3-0-0 | 3.0 | +1.774 [+1.305, +2.242] | 3-0-0 | 3.0 | +0.505 [+0.116, +0.894] |
| fitorfold | 3 | +1.089 [+0.810, +1.369] | 3-0-0 | 3.0 | +1.310 [+0.988, +1.632] | 3-0-0 | 3.0 | +0.221 [-0.049, +0.491] |
| cbetter | 3 | +1.037 [+0.507, +1.566] | 1-0-2 | 2.0 | +0.429 [-0.123, +0.981] | 1-0-2 | 2.0 | -0.607 [-0.970, -0.245] |
| nit | 3 | +1.022 [+0.817, +1.227] | 3-0-0 | 3.0 | +1.280 [+1.066, +1.494] | 3-0-0 | 3.0 | +0.258 [+0.081, +0.435] |
| tag | 3 | +0.868 [+0.578, +1.158] | 3-0-0 | 3.0 | +1.285 [+0.913, +1.657] | 3-0-0 | 3.0 | +0.417 [+0.107, +0.727] |
| trappy | 3 | +0.851 [+0.568, +1.134] | 3-0-0 | 3.0 | +0.739 [+0.416, +1.062] | 3-0-0 | 3.0 | -0.112 [-0.342, +0.118] |
| rock_shover | 3 | +0.774 [+0.548, +0.999] | 3-0-0 | 3.0 | +0.805 [+0.573, +1.037] | 3-0-0 | 3.0 | +0.031 [-0.048, +0.110] |

**4 s bank: master 44.5 / 45, +3.632 [+3.479, +3.786] (44-0-1); branch 43.5 / 45, +3.637 [+3.479, +3.795] (42-0-3)**

| opponent | N | master bb/deal [95% CI] | W-L-C | pts | branch bb/deal [95% CI] | W-L-C | pts | Δ [95% CI] |
|---|---|---|---|---|---|---|---|---|
| baseline_calling_station | 3 | +10.185 [+9.655, +10.716] | 3-0-0 | 3.0 | +9.774 [+9.240, +10.309] | 3-0-0 | 3.0 | -0.411 [-0.484, -0.338] |
| baseline_always_half | 3 | +8.742 [+7.879, +9.604] | 3-0-0 | 3.0 | +8.707 [+7.845, +9.570] | 3-0-0 | 3.0 | -0.034 [-0.180, +0.112] |
| maniac | 3 | +5.857 [+4.882, +6.832] | 3-0-0 | 3.0 | +6.018 [+5.044, +6.993] | 3-0-0 | 3.0 | +0.161 [-0.231, +0.554] |
| baseline_random | 3 | +5.755 [+4.964, +6.547] | 3-0-0 | 3.0 | +6.493 [+5.673, +7.313] | 3-0-0 | 3.0 | +0.738 [-0.030, +1.505] |
| baseline_always_pot | 3 | +5.572 [+4.587, +6.556] | 3-0-0 | 3.0 | +5.553 [+4.569, +6.536] | 3-0-0 | 3.0 | -0.019 [-0.233, +0.196] |
| lag | 3 | +4.932 [+4.315, +5.549] | 3-0-0 | 3.0 | +4.059 [+3.424, +4.695] | 3-0-0 | 3.0 | -0.872 [-1.392, -0.352] |
| potodds | 3 | +3.606 [+3.126, +4.085] | 3-0-0 | 3.0 | +3.323 [+2.820, +3.826] | 3-0-0 | 3.0 | -0.282 [-0.594, +0.029] |
| honest | 3 | +2.986 [+2.521, +3.452] | 3-0-0 | 3.0 | +2.662 [+2.181, +3.143] | 3-0-0 | 3.0 | -0.324 [-0.716, +0.068] |
| exploiter | 3 | +1.180 [+0.838, +1.522] | 3-0-0 | 3.0 | +1.552 [+1.091, +2.013] | 3-0-0 | 3.0 | +0.372 [-0.017, +0.760] |
| fitorfold | 3 | +1.137 [+0.850, +1.425] | 3-0-0 | 3.0 | +1.509 [+1.201, +1.817] | 3-0-0 | 3.0 | +0.372 [+0.120, +0.624] |
| cbetter | 3 | +1.058 [+0.534, +1.582] | 2-0-1 | 2.5 | +0.614 [+0.062, +1.167] | 1-0-2 | 2.0 | -0.444 [-0.802, -0.086] |
| nit | 3 | +0.983 [+0.781, +1.184] | 3-0-0 | 3.0 | +1.339 [+1.122, +1.555] | 3-0-0 | 3.0 | +0.356 [+0.170, +0.542] |
| trappy | 3 | +0.874 [+0.596, +1.153] | 3-0-0 | 3.0 | +0.675 [+0.352, +0.998] | 2-0-1 | 2.5 | -0.199 [-0.417, +0.019] |
| tag | 3 | +0.855 [+0.564, +1.146] | 3-0-0 | 3.0 | +1.448 [+1.072, +1.824] | 3-0-0 | 3.0 | +0.593 [+0.284, +0.903] |
| rock_shover | 3 | +0.759 [+0.535, +0.984] | 3-0-0 | 3.0 | +0.828 [+0.596, +1.059] | 3-0-0 | 3.0 | +0.068 [-0.020, +0.156] |

**Safety (hero, all 4 runs):** 0 errors, 0 forfeits, 0 bank empties (opponents also 0 / 0). Max decision CPU: branch 10.9 / 10.6 ms, master 10.7 / 9.9 ms (8 s / 4 s). Max decision wall: branch 513.8 / 34.5 ms, master 63.8 / 322.4 ms. Each side has one wall-clock spike over 100 ms in one of its two runs, while CPU stays under 11 ms, so these are scheduler stalls on the shared Mac (see the sim-load notes), not compute. Max half think: branch 5.95 / 2.96 s, master 5.81 / 3.15 s.

## Earlier measurement (pre-#70 master 748c08a, 12 bots, superseded by the section above)
### The idea
`tools/opponents/tag.py` folds to a bet whenever its Monte Carlo equity, minus 0.07 per raise we have made in the hand and 0.05 per raise this street, is below pot odds + 0.06. Against a half-pot bet (pot odds 0.25) after a preflop raise that is every hand under about 0.43 equity on the flop and 0.57 on the river: 40 to 60% of its range. `bot/postflop.py` only bluffs 10% of the time, turn and river, with equity under 0.20, so that fold equity went unused. `exploiter.py` and `nit.py` fold similarly often, the baselines and `maniac` almost never.

`bot/pressure.py` wraps `bot.postflop.postflop_action`: same equity estimate (one Monte Carlo call), same `decide()`; the only change is that when it is checked to us and `decide` would check, it bets half pot if

    EV(bet) - EV(check) > margin * pot, with
    EV(check) = eq * pot
    EV(bet)   = pf * pot - pr * b + (1 - pf - pr) * ((eq - called_shift * pf) * (pot + 2b) - b)

where pf = `OpponentModel.fold_to_bet(street)` and pr = `raise_vs_bet(street)`, both shrunk toward heads-up priors with 8 pseudo-observations, so the bet frequency only moves once the model has seen the opponent fold. Defaults: called_shift 0.20, margin 0.03, flop onward, pf >= 0.25. Cost: a few float operations per decision; no new Monte Carlo.

### Parameter sweep (screening set, 1 seed `sim-0`, 1000 deals, 8 s bank)
`tools/sweep_pressure.py --procs 3 --variants off,default,s10,s35,m0,m8,turn,potbig` (load 12 to 42). bb/deal per opponent; a 1000-deal match has a CI of roughly ±0.4 bb/deal, so single-opponent differences under that are noise.

| variant | change from default | pts / 6 | mean bb/deal | calling_station | potodds | trappy | nit | exploiter | tag | max CPU ms |
|---|---|---|---|---|---|---|---|---|---|---|
| off | module disabled (master) | 3.0 | +1.226 | +9.039 | +1.298 | +0.155 | −0.167 | −1.125 | −1.843 | 9.4 |
| **default** | called_shift 0.20, margin 0.03, flop+ | **4.0** | **+1.578** | +8.870 | +0.772 | +0.017 | +0.329 | −0.351 | −0.167 | 9.9 |
| s10 | called_shift 0.10 | 4.0 | +1.440 | +8.368 | +1.022 | −0.142 | +0.333 | −0.633 | −0.305 | 10.6 |
| s35 | called_shift 0.35 | 4.0 | +1.466 | +8.838 | +0.903 | +0.169 | +0.604 | −0.833 | −0.887 | 10.7 |
| m0 | margin 0 | 4.0 | +1.467 | +8.483 | +0.977 | −0.290 | +0.373 | −0.440 | −0.301 | 10.6 |
| m8 | margin 0.08 | 3.5 | +1.452 | +9.002 | +0.720 | +0.251 | +0.281 | −0.506 | −1.032 | 10.9 |
| turn | turn and river only | 4.0 | +1.445 | +8.850 | +0.798 | −0.019 | +0.146 | −0.344 | −0.758 | 10.4 |
| potbig | pot-size bet when pf >= 0.5 | 4.0 | +1.356 | +8.826 | +0.248 | −0.545 | +0.575 | −0.650 | −0.316 | 9.8 |

Every variant beats off. The default is best; betting the flop matters (turn-only gives back 0.6 bb/deal vs tag), pot-size bets lose to potodds and trappy, and a larger margin or called_shift bets too rarely vs tag. The gains come from tag (+1.7), exploiter (+0.8) and nit (+0.5); potodds (−0.5) and trappy (−0.1) pay for some of it. 0 errors, 0 empty banks in every run.

### Full field (12 bots, 3 seeds × 1000 deals, seed base `p68`, fresh seeds not used in the sweep)
Commands (each run once, one after the other, module toggled by `PRESSURE=off`):
```
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --seed-base p68 --time-bank 8 --procs 3 --quiet --json data/68-field-tb8-{off,on}.json
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --seed-base p68 --time-bank 4 --procs 3 --quiet --json data/68-field-tb4-{off,on}.json
```
Load (1-min) 9.8 to 13.6 throughout. Bar for reference (`findings/46-agent-grace.md`, seed base `sim`): 26.5 / 36 at 8 s, 26.0 / 36 at 4 s; the off rows here (26.5, 27.0) agree within run-to-run noise.

**8 s bank**

| opponent | off: bb/deal [95% CI] | W-L-C | pts | on: bb/deal [95% CI] | W-L-C | pts | Δ bb/deal |
|---|---|---|---|---|---|---|---|
| baseline_calling_station | +8.988 [+8.464, +9.511] | 3-0-0 | 3.0 | +8.791 [+8.266, +9.317] | 3-0-0 | 3.0 | -0.196 |
| baseline_always_half | +8.521 [+7.682, +9.361] | 3-0-0 | 3.0 | +8.667 [+7.830, +9.504] | 3-0-0 | 3.0 | +0.145 |
| baseline_random | +5.477 [+4.733, +6.222] | 3-0-0 | 3.0 | +6.059 [+5.301, +6.817] | 3-0-0 | 3.0 | +0.582 |
| maniac | +5.752 [+4.787, +6.716] | 3-0-0 | 3.0 | +5.829 [+4.861, +6.796] | 3-0-0 | 3.0 | +0.077 |
| baseline_always_pot | +5.381 [+4.406, +6.356] | 3-0-0 | 3.0 | +5.574 [+4.597, +6.550] | 3-0-0 | 3.0 | +0.193 |
| lag | +3.857 [+3.259, +4.455] | 3-0-0 | 3.0 | +3.060 [+2.442, +3.678] | 3-0-0 | 3.0 | -0.797 |
| potodds | +1.174 [+0.790, +1.558] | 3-0-0 | 3.0 | +0.611 [+0.197, +1.024] | 1-0-2 | 2.0 | -0.564 |
| nit | -0.466 [-0.777, -0.154] | 0-1-2 | 1.0 | +0.498 [+0.175, +0.822] | 1-0-2 | 2.0 | +0.964 |
| trappy | +0.723 [+0.441, +1.006] | 2-0-1 | 2.5 | +0.484 [+0.132, +0.836] | 1-0-2 | 2.0 | -0.239 |
| rock_shover | +0.412 [+0.032, +0.793] | 1-0-2 | 2.0 | +0.411 [+0.015, +0.808] | 1-0-2 | 2.0 | -0.001 |
| tag | -1.974 [-2.363, -1.584] | 0-3-0 | 0.0 | -0.524 [-1.014, -0.035] | 0-0-3 | 1.5 | +1.449 |
| exploiter | -2.108 [-2.529, -1.686] | 0-3-0 | 0.0 | -1.074 [-1.556, -0.592] | 0-2-1 | 0.5 | +1.034 |
| **total** | **+2.978** | 24-7-5 | **26.5 / 36** | **+3.199** | 22-2-12 | **28.0 / 36** | +0.221 |

**4 s bank**

| opponent | off: bb/deal [95% CI] | W-L-C | pts | on: bb/deal [95% CI] | W-L-C | pts | Δ bb/deal |
|---|---|---|---|---|---|---|---|
| baseline_calling_station | +8.998 [+8.472, +9.523] | 3-0-0 | 3.0 | +8.785 [+8.261, +9.310] | 3-0-0 | 3.0 | -0.212 |
| baseline_always_half | +8.605 [+7.765, +9.445] | 3-0-0 | 3.0 | +8.575 [+7.737, +9.414] | 3-0-0 | 3.0 | -0.029 |
| maniac | +5.794 [+4.828, +6.760] | 3-0-0 | 3.0 | +5.755 [+4.787, +6.722] | 3-0-0 | 3.0 | -0.039 |
| baseline_always_pot | +5.491 [+4.518, +6.464] | 3-0-0 | 3.0 | +5.589 [+4.611, +6.567] | 3-0-0 | 3.0 | +0.098 |
| baseline_random | +5.280 [+4.534, +6.026] | 3-0-0 | 3.0 | +5.279 [+4.533, +6.024] | 3-0-0 | 3.0 | -0.001 |
| lag | +3.670 [+3.068, +4.271] | 3-0-0 | 3.0 | +3.505 [+2.898, +4.111] | 3-0-0 | 3.0 | -0.165 |
| trappy | +0.691 [+0.403, +0.978] | 3-0-0 | 3.0 | +0.615 [+0.255, +0.974] | 1-0-2 | 2.0 | -0.076 |
| nit | -0.493 [-0.803, -0.184] | 0-1-2 | 1.0 | +0.432 [+0.104, +0.760] | 1-0-2 | 2.0 | +0.926 |
| rock_shover | +0.410 [+0.029, +0.791] | 1-0-2 | 2.0 | +0.430 [+0.033, +0.828] | 1-0-2 | 2.0 | +0.020 |
| potodds | +0.959 [+0.586, +1.331] | 3-0-0 | 3.0 | +0.326 [-0.080, +0.731] | 0-0-3 | 1.5 | -0.633 |
| tag | -1.937 [-2.336, -1.538] | 0-3-0 | 0.0 | -0.564 [-1.048, -0.080] | 0-0-3 | 1.5 | +1.373 |
| exploiter | -1.935 [-2.346, -1.523] | 0-3-0 | 0.0 | -1.069 [-1.534, -0.605] | 0-2-1 | 0.5 | +0.865 |
| **total** | **+2.961** | 25-7-4 | **27.0 / 36** | **+3.138** | 21-2-13 | **27.5 / 36** | +0.177 |


### Safety
Max call wall ms includes OS scheduling pauses on a box at load 10-20 (other sessions' sims); the bot's own CPU per call never exceeded 18 ms. No half emptied its bank (max think 5.86 s of 8, 3.12 s of 4).

| run | errors | forfeits | timeouts | max half think s | mean dec ms | max call wall ms | max call CPU ms |
|---|---|---|---|---|---|---|---|
| 8 s off | 0 | 0 | 0 | 5.86 | 2.07 | 150.8 | 10.6 |
| 8 s on | 0 | 0 | 0 | 5.84 | 2.06 | 58.5 | 18.0 |
| 4 s off | 0 | 0 | 0 | 3.12 | 1.24 | 183.1 | 10.7 |
| 4 s on | 0 | 0 | 0 | 2.92 | 1.25 | 168.9 | 10.8 |
