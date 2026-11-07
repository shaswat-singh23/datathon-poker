# Fold-equity ("pressure") betting from the opponent model's fold-to-bet rate
- Issue: #68 | Author: Kyle (Claude Code, /improve) | Time: 17:45
- Claim: `bot/pressure.py` (fold-equity betting: when checked to us postflop, bet half pot if the EV of the bet against the opponent model's measured fold-to-bet and raise-vs-bet rates beats checking) raises the field result from **26.5 to 28.0 / 36 at the 8 s bank** (+2.978 → +3.199 bb/deal) and from **27.0 to 27.5 / 36 at the 4 s bank** (+2.961 → +3.138 bb/deal), in paired off/on runs on fresh seeds. Losses drop from 7 to 2 matches at both banks: tag goes from 0/3 to 1.5/3 (−1.97 → −0.52 bb/deal at 8 s), exploiter from 0/3 to 0.5/3 (−2.11 → −1.07), nit from 1/3 to 2/3 (−0.47 → +0.50). The cost is potodds (−0.56 / −0.63 bb/deal, 3 → 2 and 1.5 points) and lag (−0.80 at 8 s, still 3/3). 0 errors, 0 forfeits, 0 empty banks in 288 hero halves; the module adds no Monte Carlo work (max CPU per call 18 ms).
- Evidence: `tools/sim.py`, duplicate format, 1000 deals per match, `--procs 3`, 10-core Mac shared with other sessions' sims (1-min load in the tables). Branch `68-pressure` on master `748c08a`. "off" is the same code with the module disabled (`PRESSURE=off`), i.e. master's play; "on" is `bot/pressure.py` at its default PARAMS. Off and on use the same seeds, so every comparison is paired by deal.
- So what: this is the first change that scores against the two Monte Carlo sparring bots (tag, exploiter), the closest stand-ins for a thinking student bot, and it does so by reading the opponent rather than by retuning thresholds, so it should carry over to unknown bots that fold too much to a half-pot bet while leaving stations alone (calling_station −0.2 bb/deal, inside noise). The potodds/lag leak (betting into bots that call or raise light) is the obvious follow-up: gate the bet on the opponent's raise-vs-bet rate more strongly, or on position. Recommend merging and making it the new submission candidate after the final SHA gate (#57).
- Checked by: unchecked

## The idea
`tools/opponents/tag.py` folds to a bet whenever its Monte Carlo equity, minus 0.07 per raise we have made in the hand and 0.05 per raise this street, is below pot odds + 0.06. Against a half-pot bet (pot odds 0.25) after a preflop raise that is every hand under about 0.43 equity on the flop and 0.57 on the river: 40 to 60% of its range. `bot/postflop.py` only bluffs 10% of the time, turn and river, with equity under 0.20, so that fold equity went unused. `exploiter.py` and `nit.py` fold similarly often, the baselines and `maniac` almost never.

`bot/pressure.py` wraps `bot.postflop.postflop_action`: same equity estimate (one Monte Carlo call), same `decide()`; the only change is that when it is checked to us and `decide` would check, it bets half pot if

    EV(bet) - EV(check) > margin * pot, with
    EV(check) = eq * pot
    EV(bet)   = pf * pot - pr * b + (1 - pf - pr) * ((eq - called_shift * pf) * (pot + 2b) - b)

where pf = `OpponentModel.fold_to_bet(street)` and pr = `raise_vs_bet(street)`, both shrunk toward heads-up priors with 8 pseudo-observations, so the bet frequency only moves once the model has seen the opponent fold. Defaults: called_shift 0.20, margin 0.03, flop onward, pf >= 0.25. Cost: a few float operations per decision; no new Monte Carlo.

## Parameter sweep (screening set, 1 seed `sim-0`, 1000 deals, 8 s bank)
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

## Full field (12 bots, 3 seeds × 1000 deals, seed base `p68`, fresh seeds not used in the sweep)
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


## Safety
Max call wall ms includes OS scheduling pauses on a box at load 10-20 (other sessions' sims); the bot's own CPU per call never exceeded 18 ms. No half emptied its bank (max think 5.86 s of 8, 3.12 s of 4).

| run | errors | forfeits | timeouts | max half think s | mean dec ms | max call wall ms | max call CPU ms |
|---|---|---|---|---|---|---|---|
| 8 s off | 0 | 0 | 0 | 5.86 | 2.07 | 150.8 | 10.6 |
| 8 s on | 0 | 0 | 0 | 5.84 | 2.06 | 58.5 | 18.0 |
| 4 s off | 0 | 0 | 0 | 3.12 | 1.24 | 183.1 | 10.7 |
| 4 s on | 0 | 0 | 0 | 2.92 | 1.25 | 168.9 | 10.8 |
