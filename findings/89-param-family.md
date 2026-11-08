# No random equity-bot beats the hero in 80 tries; the two it only chops are as strong as tag (negative result)
- Issue: #89 | Author: Shaswat (agent) | Time: 00:40
- Claim: master `644305e` loses **0 of 240 screen matches** against 80 randomly parametrized equity-threshold bots (two families of 40, 2 seeds x 1000 deals each): **79.0 / 80 pts at 8 s (+2.682 bb/deal), 78.5 / 80 at 4 s (+2.671), 77.5 / 80 at 8 s on a second family (+2.610)**. Two bots (`fam_1_017`, `fam_2_020`) are only chopped, at both banks, over 10 fresh seeds. Both are as strong as our best sparring bots: each holds `tag` and `exploiter` to a chop and loses to `trappy` (and, for one, `cbetter`). So no hero-specific hole shows up. The hero's weak spot is the same one #82 found: bots that bet thin, fold to our aggression, and call tight.
- Evidence: `tools/sweep_family.py` (new, uses `tools/gen_family.py`), hero `agent.py` at master `644305e`, 3 sweeps, one at a time, every sim started at 1-min load 0.2 to 5.0 (gate: below 8) with nothing else of mine running. Duplicate format, `--procs 5`. Logs and JSON in `/tmp/89*/` (local, not committed).
  Reproduce: `python tools/sweep_family.py --n 40 --gen-seed {1,2} --out /tmp/89x --procs 5 [--screen-bank 4]`. The bots are regenerated from `--gen-seed` (`random.Random(seed)`), so the family is not committed.
- So what: a plain "Monte Carlo equity vs a random hand, thresholds, some bluffs" bot did not beat us in 80 samples of its parameter space. The judge's win needs the 95% CI above 0, and against the hardest of these bots the hero is at about +0.1 to +0.2 bb/deal, so it is a coin-flip chop, not a loss. If a team ships a thin-betting, tight-calling bot, expect a half point from us, not a full one.
- Checked by: unchecked

## What the family is
`tools/gen_family.py` writes standalone bots in the shape `tools/sim.py` loads. They copy `tools/opponents/honest.py`'s equity code (Monte Carlo vs one random hand, ~100 samples, paced to half the bank) and differ in 16 sampled parameters:

| group | parameters (range) |
|---|---|
| preflop | `pre_pot` 0.58-0.70 and `pre_raise` 0.46-`pre_pot` (equity cutoffs for pot / half raise), `pre_slack` -0.06..+0.10 (call vs pot odds) |
| value | `val_pot` 0.62-0.92, `val_half` 0.48-0.70, `half_pref` 0-1 (size preference), `slow` 0-0.5 slow-play (40% of bots) |
| calling | `call_margin` -0.08..+0.08 over pot odds, `agg_disc` 0-0.07 equity lost per opponent bet this hand (70%), `float` 0-0.35 on the flop (50%) |
| bluffing | `bluff_flop/turn/river` 0-0.4 each (50% each), `bluff_pot` 0-1 size, `cbet` 0-1 (60%), `bluff_raise` 0-0.15 (50%) |

The family stays out of `tools/opponents/`, so the standard field glob is unchanged.

## Screen (hero vs 40 bots, 2 seeds x 1000 deals each, 80 matches per row)

| family | hero bank | points | W-L-C | mean bb/deal [95% CI] | bots under 2.0 pts | max decision ms | max half think | errors |
|---|---|---|---|---|---|---|---|---|
| seed 1 | 8 s | **79.0 / 80** | 78-0-2 | +2.682 [+2.585, +2.778] | `fam_1_017` (1.0) | 44.0 | 6.25 s | 0 |
| seed 1 | 4 s | **78.5 / 80** | 77-0-3 | +2.671 [+2.574, +2.768] | `fam_1_026` (1.5), `fam_1_017` (1.0) | 34.2 | 3.13 s | 0 |
| seed 2 | 8 s | **77.5 / 80** | 75-0-5 | +2.610 [+2.512, +2.708] | `fam_2_034`, `_011`, `_007` (1.5 each), `fam_2_020` (1.0) | 12.3 | 6.06 s | 0 |

The weakest screen result in each family is a chop (CI straddles 0): `fam_1_017` -0.201 [-0.820, +0.418] (8 s), `fam_2_020` -0.449 [-1.144, +0.246]. Opponent errors: 0 in all 240 matches.

## Confirmation (every bot under 2.0 pts, 10 fresh seeds x 1000 deals, so 10 matches each)
`fam_1_*` used seed base `cf1`, `fam_2_*` used `cf2`. `fam_1_017` was confirmed twice at each bank (once in each seed-1 sweep, same seeds); the second line is the rerun, and the two differ by up to 0.17 bb/deal because the hero's Monte Carlo budget comes from the wall clock.

| bot | 8 s bb/deal [95% CI] | 8 s W-L-C | 4 s bb/deal [95% CI] | 4 s W-L-C |
|---|---|---|---|---|
| `fam_1_017` | -0.184 [-0.457, +0.090] / -0.239 [-0.514, +0.035] | 0-1-9 / 0-0-10 | +0.087 [-0.192, +0.366] / +0.129 [-0.149, +0.408] | 0-0-10 / 0-0-10 |
| `fam_2_020` | +0.106 [-0.194, +0.405] | 0-0-10 | +0.190 [-0.112, +0.492] | 0-0-10 |
| `fam_1_026` | +0.837 [+0.601, +1.073] | 7-0-3 | +0.742 [+0.497, +0.987] | 5-0-5 |
| `fam_2_007` | +0.811 [+0.607, +1.014] | 8-0-2 | +0.846 [+0.635, +1.058] | 6-0-4 |
| `fam_2_011` | +1.011 [+0.801, +1.222] | 6-0-4 | +1.148 [+0.937, +1.359] | 10-0-0 |
| `fam_2_018` | +1.060 [+0.780, +1.339] | 8-0-2 | +1.238 [+0.953, +1.522] | 8-0-2 |
| `fam_2_034` | +1.227 [+0.975, +1.479] | 7-0-3 | +1.301 [+1.049, +1.553] | 8-0-2 |

The only loss in 160 confirmation matches is one `fam_1_017` match at 8 s (-1 of 10, in the first sweep; the rerun on the same seeds had none). Safety over the confirmations: 0 hero errors, 0 opponent errors, max hero decision 25.0 ms, max half think 6.08 s of 8 and 2.96 s of 4. The `fam_1_017` and `fam_2_020` rows are the "chop" cases: the hero never wins a match against `fam_1_017` (40 tries) or `fam_2_020` (20 tries).

## Are the chop bots weak, or is the hero missing something?
Each chop bot played the 15-bot hand-written field itself (2 seeds x 1000 deals, 8 s, seed base `chop`, `--procs 5`, load 2.7 to 4.5):

| bot | points | W-L-C | mean bb/deal | chops / ties | loses to |
|---|---|---|---|---|---|
| `fam_1_017` | 22.0 / 30 | 16-2-12 | +2.273 | `exploiter` -0.09, `tag` -0.24, `potodds` +0.44, `fitorfold`, `honest`, `nit`, `rock_shover` | `trappy` -1.46 |
| `fam_2_020` | 20.0 / 30 | 14-4-12 | +1.645 | `exploiter` +0.02, `tag` +0.36, `potodds` +0.27, `honest`, `rock_shover` | `trappy` -1.60, `cbetter` -1.67 |

(For scale: `fitorfold` and `cbetter` score 27.5 / 36 on the older 12-bot field, `findings/77`; the hero scores 44 / 45.) Both bots hold `tag` and `exploiter` to chops, the hero's own strongest sparring partners, so a hero chop with them is the same result as `tag` or `exploiter` get against each other. It is not a bug-shaped hole. Master beats `tag` 3-0 and `exploiter` 3-0 on the 15-bot field, so it is stronger than both chop bots, just not by a CI-clearing margin in 10 matches.

## Which parameters make a bot hard? (Spearman, hero bb/deal vs parameter, 80 bots, 8 s screens)
| parameter | rho | parameter | rho |
|---|---|---|---|
| `agg_disc` | **-0.72** | `pre_slack` | +0.32 |
| `call_margin` | **-0.54** | `float` | +0.33 |
| `half_pref` | -0.12 | `bluff_raise` | +0.44 |
| `val_half` | +0.23 | others | within +-0.21 |

The ten worst bots have a higher `agg_disc` (0.048 vs 0.026 overall), a higher `call_margin` (+0.041 vs +0.009), a lower `val_half` (0.537 vs 0.587), more river and turn bluffing (0.139 / 0.178 vs 0.079 / 0.128) and less `float`, `slow` and `bluff_raise`. The two chop bots share `val_half` 0.49-0.52, `call_margin` +0.06, `agg_disc` +0.054, `cbet` 0.72-0.79 and `bluff_river` 0.32-0.34. In words: **they bet half pot with almost any better-than-average hand, discount their equity when we bet, and call us only with a margin.** That is `cbetter`'s style from #82, one notch less extreme (its bet rate is probably under that gate's 90%, but I did not measure it). The hero's edge comes from other bots paying off its value bets, and these bots do not.

Correlations over 80 points are rough: the parameters were sampled independently, but `agg_disc` and `call_margin` are the only two with |rho| above 0.5, and one number does not prove the cause.

## What this does not show
- All 80 bots, like `honest`, estimate equity against a **random** hand and never adapt. A bot that models the hero (as the hero models them) is outside this family. `exploiter` and `trappy` are the only such bots in the field, and the hero beats both.
- Screen CIs from 2 matches are wide (about +-0.6). A bot whose true edge over us is under about -0.3 could pass a screen as a chop and then show up only in the 10-seed confirmation; every bot with fewer than 2.0 pts was confirmed, but a bot with 2.0 pts on a lucky pair of seeds was not.
- Only 4 s and 8 s banks were used, and the sim's wall clock includes other jobs on this box. Peak 1-min load during the three sweeps was 5.1, so timing here is cleaner than a loaded run, not worse.
- `./tools/check_build.sh` was not needed: the PR touches no `agent.py`, `bot/` or `requirements*.txt`.

## Follow-up
A thin-value, tight-calling, folds-to-aggression bot (the `fam_1_017` / `fam_2_020` shape) holds the hero to chops. #82's `vs_cbet` gate only opens for bots that bet at least 90% of their chances, so widening the gate's detector to this shape is the next experiment (filed as #90, `nice`).
