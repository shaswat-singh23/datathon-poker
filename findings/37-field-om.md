# Field sim with the opponent model merged (#37) vs #9
- Issue: #38 | Author: Shaswat (agent) | Time: 14:47
- Claim: merging the opponent model (#4, PR #37) left the field result unchanged. Master now scores **18.0 / 36** at `--time-bank 4` (W 17 L 17 C 2, mean +1.256 bb/deal). #9 had 17.5 / 36 (+1.075). At the real 8 s bank it scores **25.0 / 36** (W 21 L 7 C 8, +3.019 bb/deal), the same 25.0 / 36 as #9 (+2.977). Both deltas are inside the run-to-run noise of identical code. The model only observes for now: `bot/policy.py` feeds it every action and result, and no decision reads its stats yet (that's #12). So this checks cost, not strategy. It never raised (0 exceptions in 97,679 calls) and costs about 5 µs per call, at most 35 ms per half.
- Evidence: `tools/sim.py` with the same field as #9 (`tools/opponents/*.py baseline-bots/*.py`, 12 bots), 3 seeds × 1000 deals, duplicate format, default seed base `sim`, 15 procs on a 16-core WSL box. Code at `0256393432ee0eec83b88978cfc12f9e4b3a6877`. The only play-affecting code change since #9's commit `781248a` is the new `bot/opponent_model.py`; #34 touched analysis tools only. The two runs went one after the other, never in parallel. The 1-min load average was 2.4 before the 4 s run and 18 at the end of the 8 s run, so other work was competing for CPU. CI is pooled over the 3 seeds. W-L-C scores each match on its own.

```
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 4 --json data/37-field-om-tb4.json
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 8 --json data/37-field-om-tb8.json
```

Δ is the bb/deal change from `findings/9-field.md` (`data/9-field-tb{4,8}.json`), on the same deals.

| opponent | bb/deal [95% CI], 4 s | W-L-C | pts 4 s | #9 pts | Δ bb/deal | bb/deal [95% CI], 8 s | W-L-C | pts 8 s | #9 pts | Δ bb/deal |
|---|---|---|---|---|---|---|---|---|---|---|
| baseline_calling_station | +7.862 [+7.366, +8.357] | 3-0-0 | 3.0 | 3.0 | −0.096 | +8.806 [+8.291, +9.321] | 3-0-0 | 3.0 | 3.0 | −0.016 |
| baseline_always_half | +6.953 [+6.163, +7.743] | 3-0-0 | 3.0 | 3.0 | +0.000 | +8.608 [+7.748, +9.468] | 3-0-0 | 3.0 | 3.0 | +0.024 |
| baseline_random | +5.647 [+4.800, +6.495] | 3-0-0 | 3.0 | 3.0 | +0.149 | +6.045 [+5.297, +6.792] | 3-0-0 | 3.0 | 3.0 | −0.009 |
| baseline_always_pot | +3.550 [+2.592, +4.508] | 3-0-0 | 3.0 | 3.0 | −0.069 | +5.961 [+4.999, +6.924] | 3-0-0 | 3.0 | 3.0 | −0.040 |
| maniac | +3.477 [+2.534, +4.420] | 3-0-0 | 3.0 | 3.0 | −0.093 | +6.456 [+5.500, +7.412] | 3-0-0 | 3.0 | 3.0 | +0.421 |
| rock_shover | +0.794 [+0.402, +1.186] | 2-0-1 | 2.5 | 2.5 | −0.013 | +0.791 [+0.413, +1.170] | 2-0-1 | 2.5 | 2.5 | +0.053 |
| trappy | −0.910 [−1.243, −0.578] | 0-3-0 | 0.0 | 0.0 | +0.015 | +0.238 [−0.034, +0.511] | 1-0-2 | 2.0 | 1.5 | +0.044 |
| nit | −1.046 [−1.400, −0.692] | 0-3-0 | 0.0 | 0.0 | +0.046 | −0.431 [−0.734, −0.127] | 0-1-2 | 1.0 | 1.5 | −0.018 |
| lag | −1.198 [−1.784, −0.612] | 0-2-1 | 0.5 | 0.0 | +0.766 | +3.046 [+2.440, +3.652] | 3-0-0 | 3.0 | 3.0 | −0.053 |
| potodds | −1.986 [−2.384, −1.589] | 0-3-0 | 0.0 | 0.0 | +0.803 | +0.353 [−0.052, +0.758] | 0-0-3 | 1.5 | 1.5 | +0.342 |
| tag | −3.810 [−4.313, −3.306] | 0-3-0 | 0.0 | 0.0 | −0.033 | −1.953 [−2.362, −1.544] | 0-3-0 | 0.0 | 0.0 | −0.155 |
| exploiter | −4.264 [−4.846, −3.681] | 0-3-0 | 0.0 | 0.0 | +0.697 | −1.691 [−2.138, −1.245] | 0-3-0 | 0.0 | 0.0 | −0.083 |
| **total** | mean +1.256 [+1.067, +1.444] | 17-17-2 | **18.0 / 36** | 17.5 | +0.181 | mean +3.019 [+2.836, +3.202] | 21-7-8 | **25.0 / 36** | 25.0 | +0.042 |

Safety, hero, all 72 halves of each run:

| | #9, 4 s | now, 4 s | #9, 8 s | now, 8 s |
|---|---|---|---|---|
| errors / forfeits / bank emptied | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| max charged think time per half | 1.71 s (limit 4 s) | 1.70 s (limit 4 s) | 5.52 s (limit 8 s) | 5.48 s (limit 8 s) |
| max single decision | 73.4 ms | 94.2 ms | 243.7 ms | 109.6 ms |
| halves with a decision over 100 ms | 0 | 0 | 5 | **1** |
| mean per decision | 0.37 ms | 0.40 ms | 1.67 ms | 1.68 ms |
| mean charged think per half | 0.74 s | 0.78 s | 4.19 s | 4.16 s |
| opponent halves that emptied their own bank | 27 of 72 | 28 of 72 | 0 of 72 | 0 of 72 |

- Noise reference (why the deltas aren't real): another local session ran the same two commands, with identical `args` in the JSON, on the same commit `0256393` a few minutes earlier (`.claude/worktrees/37-field-om/data/`). Identical code on identical deals gave 17.5 vs 18.0 points at 4 s (+1.118 vs +1.256 bb/deal) and 24.5 vs 25.0 at 8 s (+3.012 vs +3.019). The largest per-opponent gap between those two runs was 0.65 bb/deal at 4 s (potodds) and 0.41 at 8 s (baseline_random). The largest per-opponent change against #9 is about the same: 0.80 at 4 s (potodds) and 0.42 at 8 s (maniac). Runs differ because Monte Carlo budgets come from the wall clock. At 4 s, how often the time-hungry opponents (lag, potodds, exploiter, tag, trappy) empty their own bank also swings with machine load: 16, 27 and 28 of 72 halves across the three 4 s runs. That swing explains the three 4 s rows that moved most (lag +0.77, potodds +0.80, exploiter +0.70). In the 8 s point changes, trappy 1.5 → 2.0 and nit 1.5 → 1.0 are matches whose CI straddles 0 flipping between chop and win/loss. Trappy flipped the same way between the two same-commit runs.
- Opponent-model cost, measured directly: timing wrappers on `OpponentModel.observe_action` / `observe_result` inside real `sim.run_match` games, one match per opponent, seed `sim-0`, 4 s bank, 12 matches in parallel. Scratch script, no repo code changed. Results: 97,679 calls, mean 5.3 µs, median 2–4 µs, 99th percentile ≤ 8.6 µs, worst single call 3.4 ms (a contention or GC spike), 0 exceptions. Per match (2 halves) the total is 16–70 ms, so at most about 35 ms per half, under 1% of a 4 s bank. The +0.03 ms change in mean per decision is too big to come from a few µs per call. It's noise: the same-commit repeat measured 0.35 ms, below #9's 0.37. Zero exceptions also means `policy._disable_model` never fired, so the model really was live in every half.
- Max decision time: the slowest call recurs on the same deal sequence in all three 8 s runs (#9, the repeat, this run): rock_shover, seed `sim-0`, half 2, at 127.9 / 109.6 / 109.6 ms. Rock_shover half 2 on other seeds also comes close (#9: `sim-1` at 172.2 ms; repeat: `sim-1` at 101.5 ms). That's the #28 equity overrun on particular deals, and the opponent model doesn't change it. The drop from 243.7 ms in #9 is #9's three ~240 ms one-offs (trappy `sim-2`, baseline_random `sim-1` and `sim-2`) not recurring, so it isn't an improvement. One half still goes over 100 ms, so #28 stays open.
- Sanity (Rule 3): an observe-only model should change nothing but timing, and nothing moved beyond same-commit noise. Against the deterministic baseline_always_half at 4 s, Δ is exactly +0.000. Nothing looks too good.
- So what: the opponent model is safe to build on. It never errors, costs nothing a judge would notice, and didn't move points. The numbers #12 (exploitative adjustments) has to beat are **18.0 / 36 at 4 s and 25.0 / 36 at 8 s**. The repeat runs also show that two runs of identical code at 3 seeds can differ by 0.5 points and 0.14 bb/deal in the mean, and by up to 0.65 bb/deal against a single opponent, on this field. Any claimed gain smaller than that needs more seeds or a repeat run.
- Checked by: unchecked
