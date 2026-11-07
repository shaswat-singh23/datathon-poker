# Wired policy (timing + preflop + postflop) vs the field
- Issue: #9 | Author: Shaswat (agent) | Time: 14:13
- Claim: wiring `bot/policy.py` to bot.timing, bot.preflop and bot.postflop scores **17.5 / 36** points at `--time-bank 4` (W 17 L 18 C 1, mean +1.075 bb/deal). The placeholder heuristic scored **7.0 / 36** (−1.626 bb/deal) on the same field and seeds (`findings/10-baseline.md`). At the real 8 s bank it scores **25.0 / 36** (W 20 L 6 C 10, +2.977 bb/deal). The opponent model (#4) isn't merged yet, so it plays no part in these numbers.
- Evidence: `tools/sim.py`, field = `tools/opponents/*.py baseline-bots/*.py` (12 bots), 3 seeds × 1000 deals, duplicate format, default seed base `sim` (the same deals as #10), code at `781248aaf06079787a45dc90e9e1a67d210e5b74`, 15 procs on a 16-core WSL box. The CI column is pooled over the 3 seeds. W-L-C scores each match on its own.

```
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 4 --json data/9-field-tb4.json
.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 8 --json data/9-field-tb8.json
```

| opponent | bb/deal [95% CI], 4 s | W-L-C | pts 4 s | placeholder pts (#10) | bb/deal [95% CI], 8 s | pts 8 s |
|---|---|---|---|---|---|---|
| baseline_calling_station | +7.957 [+7.460, +8.455] | 3-0-0 | 3.0 | 3.0 | +8.821 [+8.308, +9.335] | 3.0 |
| baseline_always_half | +6.953 [+6.163, +7.743] | 3-0-0 | 3.0 | 0.0 | +8.584 [+7.736, +9.431] | 3.0 |
| baseline_random | +5.499 [+4.648, +6.350] | 3-0-0 | 3.0 | 0.0 | +6.054 [+5.309, +6.798] | 3.0 |
| baseline_always_pot | +3.619 [+2.658, +4.580] | 3-0-0 | 3.0 | 0.0 | +6.001 [+5.039, +6.963] | 3.0 |
| maniac | +3.570 [+2.629, +4.511] | 3-0-0 | 3.0 | 0.0 | +6.035 [+5.080, +6.990] | 3.0 |
| rock_shover | +0.807 [+0.423, +1.191] | 2-0-1 | 2.5 | 3.0 | +0.739 [+0.363, +1.114] | 2.5 |
| trappy | −0.925 [−1.261, −0.590] | 0-3-0 | 0.0 | 0.0 | +0.195 [−0.092, +0.482] | 1.5 |
| nit | −1.093 [−1.442, −0.743] | 0-3-0 | 0.0 | 0.5 | −0.413 [−0.733, −0.092] | 1.5 |
| lag | −1.964 [−2.592, −1.335] | 0-3-0 | 0.0 | 0.0 | +3.099 [+2.493, +3.706] | 3.0 |
| potodds | −2.789 [−3.214, −2.365] | 0-3-0 | 0.0 | 0.5 | +0.011 [−0.398, +0.420] | 1.5 |
| tag | −3.776 [−4.292, −3.261] | 0-3-0 | 0.0 | 0.0 | −1.798 [−2.202, −1.394] | 0.0 |
| exploiter | −4.960 [−5.543, −4.377] | 0-3-0 | 0.0 | 0.0 | −1.609 [−2.051, −1.166] | 0.0 |
| **total** | mean +1.075 | 17-18-1 | **17.5 / 36** | 7.0 / 36 | mean +2.977 | **25.0 / 36** |

Safety, hero, all 72 halves of each run:

| | 4 s bank | 8 s bank |
|---|---|---|
| errors / forfeits / bank emptied | 0 / 0 / 0 | 0 / 0 / 0 |
| max charged think time per half | 1.71 s (limit 4 s) | 5.52 s (limit 8 s) |
| max single decision | 73.4 ms | **243.7 ms** (5 halves over 100 ms) |
| mean per decision | 0.37 ms | 1.67 ms |

- Sanity (Rule 3): the gain is where #10 predicted. The placeholder folded to pot-sized aggression and lost 3–4 bb/deal to maniac, always_pot and always_half. The equity-based calls now beat all three. Against the five thinking bots (tag, exploiter, potodds, lag, nit) it still loses every match at 4 s. Nothing looks too good.
- Caveats:
  1. **At 4 s, Monte Carlo barely runs.** `bot/timing.py` holds back the 1.5 s reserve plus 2.44 s of overhead allowance at the start of a 1000-hand half, so postflop mostly plays the made-hand fallback (0.37 vs 1.67 ms per decision). The gap between 17.5 and 25.0 points is mostly this. Filed as #35.
  2. **At 8 s, some decisions go over 100 ms.** Probing 3 opponents × 3 seeds at 8 s: every decision over 30 ms was postflop. Timing granted at most 34 ms, postflop handed at most 20 ms to the equity engine, and the call took 40–109 ms, worst on the turn and late in the half. That's `bot.equity.equity` overrunning its budget (#28). It's under the judge's 1 s limit, but it's a bug by AGENTS.md's rule.
  3. At 4 s, five opponents (trappy, lag, potodds, tag, exploiter) emptied their own banks in 27 of 72 halves. The sim then checks or folds for them, which helps us, so the 4 s losses to those bots would likely be bigger against full-strength versions.
- So what: the first real strategy roughly 2.5× the placeholder's points (7.0 → 17.5 at the test bank, 25.0 at the real bank) and never errors. What's left: the thinking bots, at both banks (tag and exploiter are still losses at 8 s); Monte Carlo starved at the 4 s test bank (#35); and the equity overrun (#28) before the tournament.
- Checked by: unchecked
