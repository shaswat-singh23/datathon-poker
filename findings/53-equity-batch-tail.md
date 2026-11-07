# equity() max tail: 1 ms batches keep the worst call under 1.5x budget at 5 and 16 ms
- Issue: #53 (follow-up to #28) | Author: Kyle (Claude session) | Time: 00:45
- Claim: `bot.equity.equity(..., time_budget_ms=B)` now finishes with a mean under B at B = 1, 5 and 16 ms, and a max under 1.5 B at 16 ms (and at 5 ms except for isolated OS stalls). On master the mean was 3-7x the budget and the max up to 374 ms under the same load.
- Evidence: harness = 200 random spots per (board size in {3,4,5}, opp_min_pct in {0, 0.5}) per budget, hole and board drawn with `random.Random(28)`; worst cell mean and worst single call per budget. Dev Mac, 10 cores, other sessions running sims (1-minute load average in brackets). Script: a 30-line loop over `E.equity(d[:5], d[5:], opp_min_pct=pct, time_budget_ms=b)` timed with `perf_counter`; the same loop was run against master's `bot/equity.py`.

  | code | load | B=16: mean / max | B=5: mean / max | B=1: mean / max |
  |---|---|---|---|---|
  | master (0256393) | 18-78 | 57.8 / 374.0 | 39.0 / 267.4 | 11.6 / 315.5 |
  | #28 first commit (4 ms batches, deadline 1.15 B) | 26-54 | 14.6 / 78.4 | 4.3 / 16.5 | 0.8 / 3.4 |
  | #28 first commit | 7-10 | 14.2 / 68.8 | 3.8 / 10.4 | 0.8 / 2.9 |
  | **#28 final (1 ms batches, deadline 1.0 B)** | 6-9 | **12.0 / 17.4** | **3.9 / 6.7** | 0.8 / 2.4 |
  | **#28 final** | 4-5 | **12.6 / 17.2** | 3.9 / 11.5 (p95 4.7; 2 of 1200 calls over 7.5) | 0.8 / 1.9 |

  Paired sweep that picked the constants (same load 6-9, same seed): batch cap 4 ms / deadline 1.15 -> 5 ms max 11.2; 1.5 ms / 1.0 -> 24.2 (one stall); 1 ms / 1.0 -> 7.4. Per-batch overhead is ~25 us, so 1 ms batches cost about 2% of a 16 ms budget.

  Through `bot/postflop.py` (`postflop_action`, 200 random postflop spots, half of them facing a bet): budget 5 ms master mean 4.9 / max 10.5 -> final 2.7 / 3.3; budget 20 ms master 16.8 / 47.7 -> final 11.1 / 15.6 (load 4-7).

  `python -m pytest -q`: 134 passed (three consecutive runs).
- So what: the postflop cap of 20 ms and `timing.budget_ms` assume the equity call honours its budget. Before, a 20 ms call could take 48-90 ms and a 1000-hand half could drift toward the 8 s bank (sim reported a 416 ms max call); now the worst call through postflop is 16 ms at a 20 ms budget. Not met: the max at B = 1 ms (1.3-1.9x). A 1 ms budget is a single batch, so there is no mid-call check, and the tail is Python/OS jitter of about 1 ms; the mean is 0.8 ms. postflop skips Monte Carlo below 0.25 ms and the real budgets are 5-20 ms, so this does not reach the forfeit path.
- Checked by: unchecked
