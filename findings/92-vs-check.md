# Bet when the opponent checks to us: beats a copy of our own bot, points-neutral on the field
- Issue: #92 | Author: Kyle (Claude Code) | Time: 10:31
- Claim: `bot/vs_check.py` (v2, `f0edd89`) turns our postflop check into a half-pot bet when the opponent has checked to us on this street, unless the opponent called one of our postflop bets earlier in the hand, and switches off against never-folders. **Against a copy of our own bot (module off) it scores +0.630 bb/deal [+0.439, +0.820], 5-0-1 over 6 matches** (v1 without the called-bet rule: +1.115 [+0.889, +1.340], 6-0-0). On the 15-bot field it is points-neutral within run-to-run noise: **43.5 vs 41.5 / 45 at 8 s, 42.5 vs 43.0 / 45 at 4 s**, mean bb/deal +3.541 vs +3.522 and +3.622 vs +3.537. 0 errors, forfeits and timeouts in every run. No match lost.
- Evidence: `tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --procs 3 --time-bank {8,4}` (default seed base `sim`, 45 matches per row), branch from this worktree and master `644305e` from the main checkout, **run side by side at the same time** so both see the same machine load. Copy match: `tools/sim.py agent.py <copy> --seeds 6 --seed-base mir92`, where `<copy>` loads this branch's `agent.py` and sets `memory["_vs_check_off"] = True` in `new_half` (identical to master's play). JSON in the session scratchpad (not committed).
- So what: most teams' bots were likely written by AI and look like ours: bet when equity clears a threshold, check otherwise, never trap. Against those, a check means weakness, and matches between near-identical bots are chops (0.5 points). This module wins that matchup instead, and costs nothing measurable against the rest of our field.
- Checked by: unchecked

## Why
Before this module existed, a scratch wrapper (our bot plus "bet when checked to") beat plain us +0.93 bb/deal (5-0-1) and gained +0.41 tag, +0.49 honest, +0.79 exploiter on fresh seeds, but lost -1.49 bb/deal to `baseline_calling_station`. So the module switches off once the opponent has faced 12 of our postflop bets and its pooled postflop fold rate (shrunk toward 0.40 with weight 8) is below 0.18. The opponent model shrinks each street separately, so pooling matters: per-street rates would keep a never-folder above the cutoff for about 40 bets.

## Field results (hero = branch or master, 45 matches per row, same seeds, run in parallel)

| version | bank | branch points | master points | branch bb/deal | master bb/deal | branch W-L-C | max decision CPU ms (branch / master) |
|---|---|---|---|---|---|---|---|
| v1 `9965fd2` | 8 s | 42.0 | 43.0 | +3.707 | +3.508 | 39-0-6 | 10.9 / 10.6 |
| v1 `9965fd2` | 4 s | 42.5 | 42.5 | +3.686 | +3.513 | 40-0-5 | 10.9 / 10.6 |
| **v2 `f0edd89`** | 8 s | **43.5** | 41.5 | +3.541 | +3.522 | 42-0-3 | 10.7 / 10.9 |
| **v2 `f0edd89`** | 4 s | **42.5** | 43.0 | +3.622 | +3.537 | 40-0-5 | 11.6 / 11.3 |

- **Noise:** master on the same seeds scored 43.0 then 41.5 at 8 s, and 42.5 then 43.0 at 4 s. Swings of 1 to 1.5 points between identical runs are noise from Monte Carlo sampling under varying load, so neither version's points difference is significant.
- **v1 lost two trappy matches at 8 s** (trappy -0.35 bb/deal, 3.0 to 1.5 points). `trappy` check-calls strong hands on the flop and turn, then raises the river, so v1 kept betting into it after being called. v2 adds the called-bet rule: trappy is +0.10 at 8 s and -0.02 at 4 s. Its 4 s 2.0 vs 3.0 points is one match ending in a chop at the same bb/deal.
- **Calling station:** -0.01 / -0.09 bb/deal in v2 (was -1.49 with no switch), so the switch works.
- **Biggest v2 gains:** tag +0.30, potodds +0.27, cbetter +0.27 at 8 s; honest +0.32, exploiter +0.27, fitorfold +0.23 at 4 s.
- **Wall-clock spikes:** max single-decision wall time reached 84 to 156 ms in both branch and master runs (CPU never above 11.6 ms), because the two sims ran in parallel on a loaded Mac. Same for both arms, so this is a load artifact, not this module (it adds no Monte Carlo work).

## Decision
Ship rule set on #92: points >= master at both banks, 0 errors, wins vs a copy, `check_build` passes. v2 passes at 8 s (+2.0) and misses at 4 s by 0.5 (one trappy chop at equal bb/deal), both within the measured 1 to 1.5 point noise. It wins vs a copy (5-0-1) and has higher mean bb/deal at both banks. **Recommend v2 if the team expects a field of AI-written equity bots. Resubmitting is the decider's call.**
