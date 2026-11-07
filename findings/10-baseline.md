# Baseline: starter check/fold bot and placeholder heuristic vs the field
- Issue: #10 | Author: Kyle (agent) | Time: 13:19
- Claim: the organizers' starter bot (check if free, else fold) scores **0.0 / 36** points against the field (-0.950 bb/deal). Our placeholder heuristic (`bot/policy.py` at master `92deff5`) scores **7.0 / 36** (W 6 L 28 C 2), yet its mean of -1.626 bb/deal is *worse*. Every later strategy must beat 7.0 / 36 points.
- Evidence: `tools/sim.py`, field = `tools/opponents/*.py baseline-bots/*.py` (12 bots), 3 seeds × 1000 deals, duplicate format, `--time-bank 4`, master `92deff5276f1468d44c98f58ee5911fccd5a6aed`. Points: win if the 95% CI of bb/deal is above 0, loss if below, chop otherwise. The CI column is pooled over the 3 seeds. W-L-C scores each of the 3 matches on its own.

Starter (`git show 33f5db3:agent.py > <scratch>/starter_agent.py`, kept outside the repo):
```
.venv/bin/python tools/sim.py --hero <scratch>/starter_agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --deals 1000 --time-bank 4 --procs 5 --quiet --json <scratch>/starter.json
```
| opponent | bb/deal [95% CI] | W-L-C | pts |
|---|---|---|---|
| rock_shover | -0.141 [-0.157, -0.126] | 0-3-0 | 0.0 |
| nit | -0.264 [-0.287, -0.241] | 0-3-0 | 0.0 |
| trappy | -0.478 [-0.509, -0.448] | 0-3-0 | 0.0 |
| baseline_calling_station | -0.492 [-0.527, -0.457] | 0-3-0 | 0.0 |
| potodds | -0.731 [-0.765, -0.696] | 0-3-0 | 0.0 |
| baseline_random | -1.057 [-1.082, -1.032] | 0-3-0 | 0.0 |
| tag | -1.077 [-1.106, -1.049] | 0-3-0 | 0.0 |
| exploiter | -1.220 [-1.244, -1.196] | 0-3-0 | 0.0 |
| lag | -1.434 [-1.446, -1.421] | 0-3-0 | 0.0 |
| maniac | -1.500 [-1.500, -1.500] | 0-3-0 | 0.0 |
| baseline_always_half | -1.500 [-1.500, -1.500] | 0-3-0 | 0.0 |
| baseline_always_pot | -1.500 [-1.500, -1.500] | 0-3-0 | 0.0 |
| **total** | mean -0.950 | 0-36-0 | **0.0 / 36** |

Timing: max single decision 2.3 ms, max charged think time per half 0.00 s (raw 0.02 s), 0 errors.

Placeholder (`agent.py` → `bot/policy.py`):
```
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --deals 1000 --time-bank 4 --procs 5 --quiet --json <scratch>/placeholder.json
```
| opponent | bb/deal [95% CI] | W-L-C | pts |
|---|---|---|---|
| baseline_calling_station | +0.894 [+0.846, +0.942] | 3-0-0 | 3.0 |
| rock_shover | +0.263 [+0.199, +0.326] | 3-0-0 | 3.0 |
| nit | -0.407 [-0.634, -0.180] | 0-2-1 | 0.5 |
| potodds | -0.668 [-0.905, -0.431] | 0-2-1 | 0.5 |
| tag | -1.138 [-1.307, -0.969] | 0-3-0 | 0.0 |
| exploiter | -1.304 [-1.472, -1.136] | 0-3-0 | 0.0 |
| baseline_random | -1.763 [-1.958, -1.568] | 0-3-0 | 0.0 |
| lag | -1.858 [-2.053, -1.664] | 0-3-0 | 0.0 |
| trappy | -2.301 [-2.675, -1.928] | 0-3-0 | 0.0 |
| baseline_always_half | -3.053 [-3.126, -2.981] | 0-3-0 | 0.0 |
| maniac | -3.996 [-4.147, -3.846] | 0-3-0 | 0.0 |
| baseline_always_pot | -4.183 [-4.347, -4.018] | 0-3-0 | 0.0 |
| **total** | mean -1.626 | 6-28-2 | **7.0 / 36** |

Timing: max single decision 6.9 ms, max charged think time per half 0.01 s (raw 0.06 s), 0 errors.

- Sanity (Rule 3): neither result looks too good. Check/fold loses exactly 1.5 bb/deal (both blinds, one per seat) to every never-fold bot (maniac, always_half, always_pot), as the rules predict, so the sim's accounting checks out. The placeholder wins only against the two most passive bots (calling station, rock_shover).
- So what: the bar for any strategy PR is **more than 7.0 / 36 points** on this field. Points and bb/deal disagree here. The placeholder beats check/fold on points but loses more chips, mostly to the aggressive never-fold bots: -3 to -4 bb/deal vs maniac, always_pot and always_half, where check/fold loses only 1.5. It folds too much to pot-sized aggression. Beating the aggressive bots is the biggest open source of points. Both bots are far inside the time limits.
- Checked by: unchecked
