# A river-only polarized bettor is not a gap: hero wins 12-0-0 at both banks, and the line discount is worth +1.1 bb/deal against it
- Issue: #87 | Author: Shaswat (agent) | Time: 00:05
- Claim: The hypothesis was that the hero over-folds to a bot that is passive on the flop and turn and polarized on the river (strong hands plus bluffs), because the line discount scales with whole-hand postflop aggression and so reads that bot's river bets as pure strength. **It is false for the bot I built.** Hero vs `tools/opponents/riverbluff.py`: **+2.890 bb/deal [+2.680, +3.101], 12-0-0, 12.0 / 12 points at the 8 s bank; +2.918 [+2.709, +3.127], 12-0-0, 12.0 / 12 at 4 s** (12 seeds x 1000 deals each). Turning the discount down makes things worse, not better: `bet_discount` 0.0 costs **-1.127 +- 0.166 bb/deal** (paired), 0.1 costs -0.385 +- 0.066. No code change to the hero is warranted; only the new sparring bot ships.
- Evidence: `tools/sim.py --hero agent.py --field tools/opponents/riverbluff.py --seeds 12 --seed-base rb --time-bank {8,4} --procs 4` on master `644305e` plus the new bot file. Discount sweep: `python tools/sweep_cbet.py --opp tools/opponents/riverbluff.py --seeds 12 --seed-base rbs --time-bank 8 --variants '{}' '{"bet_discount":0.0}' '{"bet_discount":0.1}' '{"call_margin":0.0,"bet_discount":0.0}'` (same deals in every variant). River-bet response counts: `--seeds 3 --seed-base rbl --time-bank 8 --logs` and a throwaway script over the hand logs (not committed). Every run started at 1-minute load 0.2 to 3.3 (gate: below 8) with no other sim running.
- So what: it records that a second plausible student style (late-street polarization) does not beat or chop the hero, so nobody needs to retry it with this shape. The bot goes into the sparring field as a 16th opponent.
- Checked by: unchecked

## The bot
`tools/opponents/riverbluff.py` (copied from `honest.py`'s equity code, new decision rule). Preflop: raise half pot above 0.60 estimated equity, otherwise call when equity beats pot odds + 0.03. Flop and turn: never bets; calls when equity beats pot odds + 0.03; pot-raises above 0.85. River, when checked to: bet pot above 0.68 equity (value), bet pot with 40% of hands below 0.35 equity (bluff), otherwise check. Its whole-half postflop aggression is therefore low (bets only on the river), so the hero's `discount_scale` sits at 1 and each bet costs 0.20 equity.

## Head to head (hero vs riverbluff, 12 seeds x 1000 deals, duplicate format)
| bank | seed base | bb/deal [95% CI] | W-L-C | points | hero max decision (wall) | max half think | errors / forfeits / timeouts (both bots) |
|---|---|---|---|---|---|---|---|
| 8 s | `rb` | +2.890 [+2.680, +3.101] | 12-0-0 | 12.0 / 12 | 11.5 ms | 5.93 s | 0 / 0 / 0 |
| 4 s | `rb` | +2.918 [+2.709, +3.127] | 12-0-0 | 12.0 / 12 | 10.7 ms | 2.91 s | 0 / 0 / 0 |

For scale, the existing bots in findings/68 give +0.8 to +1.1 for the hard ones (`cbetter`, `tag`, `trappy`, `rock_shover`, `nit`) and +3.0 to +10 for the weak ones. `riverbluff` sits with `honest` (+3.06) and `potodds` (+3.4).

## Does the discount over-fold? (paired sweep, seed base `rbs`, 12 seeds, 8 s)
| variant (PARAMS override) | bb/deal | paired delta vs control | points |
|---|---|---|---|
| control (master) | +2.877 | | 12.0 / 12 |
| `bet_discount` 0.0 | +1.750 | -1.127 +- 0.166 | 12.0 / 12 |
| `bet_discount` 0.1 | +2.491 | -0.385 +- 0.066 | 12.0 / 12 |
| `bet_discount` 0.0 and `call_margin` 0.0 | +1.415 | -1.462 +- 0.139 | 12.0 / 12 |

Less discount means more calls of its river bets, and those calls lose, so the folds pay. I did not measure the value-to-bluff split of its river range; the sweep is the evidence, not a range count.

## What the hero does when it bets the river (3 seeds, 6000 hands, 8 s, hand logs)
The bot opens the river betting in 742 of 6000 hands (12.4%). The hero folds 511 (69%, average net -8.69 chips), calls 203 (27%, +7.59) and raises 28 (4%, +53.50). A 69% fold rate looks like a leak but the sweep above says it is not one: the calls it does make profit, and widening them costs chips.

## Limits
- One parameterization: bluff rate 40% of weak hands, value above 0.68, pot-size only. A bot that bluffs far more (80% or more of its weak hands) would punish a 69% fold rate; I did not build it. The hero's discount stays at full strength while a bot's whole-half postflop aggression is below 0.25 (`disc_aggr_lo`), and a river-only bluffer stays well below that, so this is the remaining risk.
- I only moved the discount down. A street-specific aggression estimate (river aggression separate from flop and turn) was not built, because there is no measured gap to fix.
- `./tools/check_build.sh` could not run in this session: Docker is not running on this machine ("CHECK FAILED: Docker isn't running"). The PR touches no file that script builds (no `agent.py`, `bot/`, `requirements*.txt`); it adds one sparring bot and this file. The reviewer should run it on the exact commit. `python -m pytest -q`: 474 passed.
