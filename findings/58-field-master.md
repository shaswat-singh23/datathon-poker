# Field rerun on master after #48 and #49: 25.0 / 36 at 4 s, 26.0 / 36 at 8 s
- Issue: #58 | Author: Kyle (Claude Code) | Time: 16:35
- Claim: master at `3868baf68dc70d0ba9323dc23c3cdddc2890feb2` scores **25.0 / 36 at the 4 s test bank** (W 21 L 7 C 8, mean **+3.119 [+2.935, +3.302] bb/deal**) and **26.0 / 36 at the real 8 s bank** (W 23 L 7 C 6, mean **+3.243 [+3.060, +3.426] bb/deal**). Both runs were on a quiet box (1-min load 8.1 to 12.4 throughout). Across all 288 hero halves in four runs: 0 errors, 0 forfeits, 0 bank empties. The 4 s gap to 8 s has nearly closed: 1 point and 0.12 bb/deal, down from 7 points in #38. At 4 s the gain over #38 (+7 points, +1.86 bb/deal) is real. At 8 s the change (+1 point, +0.22 bb/deal) is inside the run-to-run noise of the old code.
- Evidence: `tools/sim.py`, 3 seeds × 1000 deals, duplicate format, default seed base `sim`, the same 12-bot field as #9, #38 and #35, `--procs 3` on the 10-core Mac. Runs went one after the other, never in parallel. JSON in `data/58-field-tb{4,8}{,-r2}.json` (local, gitignored).

```
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 4 --procs 3 --json data/58-field-tb4.json
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 8 --procs 3 --json data/58-field-tb8.json
# reruns, gated to start only below load 10: same commands with --json data/58-field-tb{4,8}-r2.json
```

Master moved during and after the runs. #60 (tools/sim.py CPU-time column, 16:16 local) and #55 (`bot/exploit.py`, 16:19) merged while the reruns were starting. Neither changes play: `bot/policy.py` doesn't call `bot/exploit.py` yet. #61 (#46, agent.py time accounting + `bot/timing.py`, 16:32) merged after every run here. So these numbers are master **before #46**. #46's own field runs on its rebased commit (`findings/46-agent-grace.md`: 26.0 / 36 at 4 s, 26.5 and 25.5 / 36 at 8 s) are the after-#46 numbers, and they agree with this file within noise.

## Load (1-min load average, sampled every 15 s during each run)

| run | start | before | during (min to max) | after | used? |
|---|---|---|---|---|---|
| 4 s, first | 16:03:15 | 14.7 | 14.7 to **44.5** | 35.4 | no, rerun (crossed 15) |
| 8 s, first | 16:06:50 | 14.2 | 13.9 to **32.5** | 35.8 | no, rerun (crossed 15) |
| 4 s, rerun | 16:17:00 | 9.7 | 9.7 to 12.4 | 12.1 | **yes: headline** |
| 8 s, rerun | 16:19:32 | 8.5 | 8.1 to 11.1 | 9.1 | **yes: headline** |

The first runs are kept as a repeat measurement. Every opponent kept its own bank in all 72 halves of all four runs, so load didn't flatter them. They scored 26.0 / 36 (+3.037) at 4 s and 26.0 / 36 (+3.297) at 8 s.

## Per opponent (headline = reruns)

Δ is the rerun's bb/deal minus #38's (`findings/37-field-om.md`, commit `0256393`, same seeds and deals). "#48" is `findings/35-timing-4s.md` (the `bot/timing.py` now on master, before #49, 3 procs, paired with master `0256393`). "#47" is `findings/35-timing-mc-tb4.md` (the superseded timing variant, `--procs 5`, load 34 to 127).

| opponent | 4 s bb/deal [95% CI] | W-L-C | pts | Δ vs #38 | 4 s pts: #38 / #47 / #48 | 8 s bb/deal [95% CI] | W-L-C | pts | Δ vs #38 | 8 s pts: #38 / #47 / #48 |
|---|---|---|---|---|---|---|---|---|---|
| baseline_calling_station | +8.946 [+8.423, +9.470] | 3-0-0 | 3.0 | +1.08 | 3 / 3 / 3 | +8.937 [+8.410, +9.463] | 3-0-0 | 3.0 | +0.13 | 3 / 3 / 3 |
| baseline_always_half | +8.828 [+7.974, +9.682] | 3-0-0 | 3.0 | +1.88 | 3 / 3 / 3 | +9.309 [+8.460, +10.158] | 3-0-0 | 3.0 | +0.70 | 3 / 3 / 3 |
| maniac | +6.228 [+5.270, +7.186] | 3-0-0 | 3.0 | +2.75 | 3 / 3 / 3 | +6.348 [+5.385, +7.311] | 3-0-0 | 3.0 | −0.11 | 3 / 3 / 3 |
| baseline_always_pot | +6.051 [+5.080, +7.022] | 3-0-0 | 3.0 | +2.50 | 3 / 3 / 3 | +6.122 [+5.156, +7.088] | 3-0-0 | 3.0 | +0.16 | 3 / 3 / 3 |
| baseline_random | +5.911 [+5.144, +6.678] | 3-0-0 | 3.0 | +0.26 | 3 / 3 / 3 | +5.665 [+4.904, +6.427] | 3-0-0 | 3.0 | −0.38 | 3 / 3 / 3 |
| lag | +3.556 [+2.957, +4.155] | 3-0-0 | 3.0 | **+4.75** | 0.5 / 2.0 / 1.5 | +4.040 [+3.444, +4.635] | 3-0-0 | 3.0 | +0.99 | 3 / 3 / 3 |
| rock_shover | +0.777 [+0.413, +1.142] | 2-0-1 | 2.5 | −0.02 | 2.5 / 2.5 / 2.5 | +0.749 [+0.381, +1.116] | 2-0-1 | 2.5 | −0.04 | 2.5 / 2.5 / 2.5 |
| potodds | +0.549 [+0.143, +0.956] | 1-0-2 | 2.0 | **+2.54** | 0 / 0 / 0 | +1.090 [+0.705, +1.475] | 3-0-0 | 3.0 | +0.74 | 1.5 / 3.0 / 3.0 |
| trappy | +0.331 [+0.057, +0.605] | 0-0-3 | 1.5 | +1.24 | 0 / 1.5 / 1.5 | +0.361 [+0.099, +0.624] | 0-0-3 | 1.5 | +0.12 | 2.0 / 1.5 / 1.5 |
| nit | −0.380 [−0.692, −0.068] | 0-1-2 | 1.0 | +0.67 | 0 / 1.0 / 1.0 | −0.452 [−0.763, −0.140] | 0-1-2 | 1.0 | −0.02 | 1.0 / 1.0 / 1.0 |
| exploiter | −1.480 [−1.905, −1.055] | 0-3-0 | 0.0 | **+2.78** | 0 / 0 / 0 | −1.628 [−2.057, −1.199] | 0-3-0 | 0.0 | +0.06 |
| tag | −1.895 [−2.297, −1.493] | 0-3-0 | 0.0 | +1.92 | 0 / 0 / 0 | −1.626 [−2.025, −1.227] | 0-3-0 | 0.0 | +0.33 |
| **total** | mean **+3.119** [+2.935, +3.302] | 21-7-8 | **25.0 / 36** | **+1.86** | 18.0 / 22.0 / 21.5 | mean **+3.243** [+3.060, +3.426] | 23-7-6 | **26.0 / 36** | +0.22 | 25.0 / 26.0 / 26.0 |

Mean bb/deal of the comparison runs. 4 s: #38 +1.256, #47 +2.245, #48 +2.026. 8 s: #38 +3.019, #47 +3.238, #48 +3.252.

## Safety, hero, 72 halves per run

| | 4 s rerun | 4 s first | 8 s rerun | 8 s first | #38 4 s | #38 8 s |
|---|---|---|---|---|---|---|
| errors / forfeits / bank emptied | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| max charged think per half | 2.13 s (of 4) | 2.27 s | 4.61 s (of 8) | 4.49 s | 1.70 s | 5.48 s |
| mean charged think per half | 0.87 s | 0.93 s | 3.54 s | 3.62 s | 0.78 s | 4.16 s |
| max raw compute per half | 2.41 s | 2.53 s | 5.08 s | 5.11 s | n.a. | n.a. |
| mean per decision (wall) | 0.558 ms | 0.566 ms | 1.506 ms | 1.528 ms | 0.40 ms | 1.68 ms |
| max single decision (wall) | **70.3 ms** | 204.4 ms | **89.0 ms** | 126.2 ms | 94.2 ms | 109.6 ms |
| halves with a decision over 100 ms | **0** | 5 | **0** | 4 | 0 | 1 |
| opponent halves that emptied their own bank | 0 | 0 | 0 | 0 | 28 | 0 |

On the quiet reruns, no decision went over 100 ms at either bank. In #38, rock_shover `sim-0` half 2 reached 109.6 ms at 8 s, a recurring #28 equity overrun. In this rerun the same half peaks under 89 ms, consistent with #49 capping equity to its budget. The over-100 ms calls in the first runs (rock_shover half 2 at 4 s, calling_station at 8 s, up to 204 ms) all came while load was 18 to 44, and none recurred on the quiet rerun. That's OS scheduling, not a code path.

## Is the change from #38 real or noise?
Noise reference, from #38's same-commit repeat: identical code differed by 0.5 points and up to 0.14 bb/deal in the mean, and by up to 0.65 bb/deal against one opponent at 4 s (0.41 at 8 s). Across the four runs of #38's commit `0256393` at 8 s (#9, #38, the #38 repeat, #35's paired rerun), the spread was 24.5 to 25.5 points and +3.012 to +3.212 bb/deal. This ticket's own repeat (first run vs rerun) moved by 1.0 point / 0.08 bb/deal at 4 s (max per opponent 0.68, baseline_random) and by 0 points / 0.05 bb/deal at 8 s (max per opponent 0.29, exploiter).

- **4 s: real.** +7.0 points and +1.86 bb/deal over #38 is more than 10 times the same-commit spread. Every Monte Carlo-dependent opponent moved by more than 0.65 bb/deal: lag +4.75, exploiter +2.78, maniac +2.75, potodds +2.54, always_pot +2.50, tag +1.92, trappy +1.24, nit +0.67. The deterministic rock_shover moved −0.02. The first run, taken under load, agrees (26.0, +3.037).
- **8 s: inside noise.** +1.0 point and +0.22 bb/deal against #38 is just above #38's single repeat spread. But +3.243 sits right at the top of the +3.012 to +3.212 range that the old commit itself produced across four runs. The only rows past 0.65 are lag (+0.99) and potodds (+0.74). Against #35's paired 8 s run of the old commit (25.5 points, +3.177; lag +3.871, potodds +0.826), both shrink to +0.17 and +0.26. The two point changes are potodds 1.5 → 3.0 and trappy 2.0 → 1.5, matches whose CI sits close to 0. Read 8 s as "unchanged, no regression".

## Where the 4 s gain came from (Rule 3 check)
The 4 s result is 3.5 points above #48's own finding (21.5 / 36), so I ran a control under the same quiet conditions: the #48 branch tip without #49 (`bab4fb1`, extracted with `git archive` to a scratch dir, same command at 4 s, load 7.5 to 13.3). It scored **23.0 / 36, +2.651 [+2.466, +2.836] bb/deal**, 0 errors, max decision 104.8 ms (1 half over 100 ms).
- #48's 21.5 → 23.0 (+0.6 bb/deal): the quieter machine. #48's paired runs used a busier box, so its wall-clock budgets bought fewer samples.
- 23.0 → 25.0 (+0.47 bb/deal): #49. It lands mostly on potodds (−2.57 → +0.55, 0 → 2.0 pts) and lag (+2.04 → +3.56), with tag +0.15 and exploiter +0.02. That fits #49's purpose: equity keeps to its budget, so the timing planner stops counting the overrun as overhead and grants more of the bank as real samples. This is one paired run per side. The potodds row has swung 1 to 2 bb/deal between runs before (#47, #48), so treat the split as approximate.

## So what
- **Headline for AGENTS.md: 26.0 / 36 at the real 8 s bank (+3.24 bb/deal), 25.0 / 36 at the 4 s test bank (+3.12), 0 errors in 288 halves.**
- The 4 s test bank now plays nearly the same game as the real bank, a 1-point gap instead of 7. #39 and #56 can tune at `--time-bank 4` and trust the result to carry over. Their same-commit baseline is the rerun JSON above.
- The remaining losses are all strategy, not time. Tag (−1.6 to −1.9) and exploiter (−1.5 to −1.6) are 0 / 6 at both banks. Of the 10 points lost at 8 s, those two account for 6, nit for 2 (0-1-2), trappy for 1.5 (three chops) and rock_shover for 0.5.
- Checked by: unchecked
