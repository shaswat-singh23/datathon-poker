# equity() timing: 1 ms batches reduce overruns; shared-machine stalls remain
- Issue: #53 (follow-up to #28) | Author: Kyle (Claude session) | Time: 00:45
- Claim: the PR's `bot.equity.equity(..., time_budget_ms=B)` has a mean under B at B = 1, 5 and 16 ms in the recorded sweeps. The loaded reviewer runs show a substantial reduction in calls over 1.5 B at B = 5 ms. Smaller batches do not guarantee a worst call under 1.5 B on a shared machine: reviewer runs at B = 16 ms reached 53.8 and 92.4 ms. The original pre-#28 implementation reached 374 ms; that is a historical comparison, distinct from this PR's baseline with 4 ms batches.
- Evidence: historical harness = 200 random spots per (board size in {3,4,5}, opp_min_pct in {0, 0.5}) per budget, hole and board drawn with `random.Random(28)`; worst cell mean and worst single call per budget. Dev Mac, 10 cores, other sessions running sims (1-minute load average in brackets). Script: a 30-line loop over `E.equity(d[:5], d[5:], opp_min_pct=pct, time_budget_ms=b)` timed with `perf_counter`; the same loop was run against master's `bot/equity.py`. These historical rows retain the measurements originally recorded; unrecorded percentiles and outlier counts cannot be recovered from their mean/max summaries. Complete distributions from fresh paired runs are below.

  Historical measurements (all times in ms):

  | code | load | B=16: mean / max | B=5: mean / max | B=1: mean / max |
  |---|---|---|---|---|
  | master (0256393) | 18-78 | 57.8 / 374.0 | 39.0 / 267.4 | 11.6 / 315.5 |
  | #28 first commit (4 ms batches, deadline 1.15 B) | 26-54 | 14.6 / 78.4 | 4.3 / 16.5 | 0.8 / 3.4 |
  | #28 first commit | 7-10 | 14.2 / 68.8 | 3.8 / 10.4 | 0.8 / 2.9 |
  | **this PR (1 ms batches, deadline 1.0 B)** | 6-9 | **12.0 / 17.4** | **3.9 / 6.7** | 0.8 / 2.4 |
  | **this PR** | 4-5 | **12.6 / 17.2** | 3.9 / 11.5 (p95 4.7; 2 of 1200 calls over 7.5) | 0.8 / 1.9 |

  Paired sweep that picked the constants (same load 6-9, same seed): batch cap 4 ms / deadline 1.15 -> 5 ms max 11.2; 1.5 ms / 1.0 -> 24.2 (one stall); 1 ms / 1.0 -> 7.4. Per-batch overhead is ~25 us, so 1 ms batches cost about 2% of a 16 ms budget.

  Through `bot/postflop.py` (`postflop_action`, 200 random postflop spots, half of them facing a bet): budget 5 ms master mean 4.9 / max 10.5 -> final 2.7 / 3.3; budget 20 ms master 16.8 / 47.7 -> final 11.1 / 15.6 (load 4-7).

  Historical `python -m pytest -q`: 134 passed (three consecutive runs); Kyle's review on `ce8cce9` subsequently recorded 141 passed three times.

  Paired rerun method (2026-11-07, Sahith / Codex): baseline `3868baf68dc70d0ba9323dc23c3cdddc2890feb2` (PR base, 4 ms batches / deadline 1.15 B) versus PR `ce8cce9f84c3a17c7a2598ab43906a743fbd9df8` (1 ms / 1.0 B). `bot/equity.py` is identical between that baseline and current master `4464f11708ff78e7ae2d28819d2c84a4f0c52b22`. Two alternating baseline/PR runs, each in a fresh Python process; each budget resets the card generator to `Random(28)` and uses a NumPy generator seeded 28. Each budget has six cells of 200 spots, checked before pooling: **1200 calls per budget per run, 14,400 total**. Mean is the worst of the six cell means; max, p95, p99 (NumPy linear interpolation), and strict `time > 1.5 B` counts pool all 1200 calls. All values are elapsed wall time in ms. This is a new measurement on WSL, not a reconstruction of the Mac samples.

  Environment: Python 3.12.3, NumPy 2.5.4, WSL2 Linux 6.6.87.2 x86_64, 8 logical CPUs. One-minute load at the start/end of successive runs: 1.15/1.11, 1.11/1.08, 1.08/1.14, 1.14/1.10. No other tests or benchmark sweeps were launched by this session while timing.

  | code / run | B (ms) | worst-cell mean | max | p95 | p99 | calls > 1.5 B |
  |---|---|---|---|---|---|---|
  | baseline 1 | 16 | 13.544 | 18.278 | 14.184 | 15.691 | 0 / 1200 |
  | PR 1 | 16 | 13.435 | 25.852 | 14.697 | 15.879 | 1 / 1200 |
  | baseline 2 | 16 | 11.701 | 30.598 | 14.268 | 17.353 | 1 / 1200 |
  | PR 2 | 16 | 13.233 | 17.969 | 14.197 | 15.640 | 0 / 1200 |
  | baseline 1 | 5 | 4.511 | 8.240 | 5.212 | 6.069 | 1 / 1200 |
  | PR 1 | 5 | 4.404 | 13.437 | 4.834 | 5.237 | 4 / 1200 |
  | baseline 2 | 5 | 4.532 | 7.480 | 5.008 | 5.703 | 0 / 1200 |
  | PR 2 | 5 | 4.095 | 5.280 | 4.675 | 4.966 | 0 / 1200 |
  | baseline 1 | 1 | 0.990 | 3.152 | 1.169 | 1.480 | 11 / 1200 |
  | PR 1 | 1 | 0.937 | 1.939 | 1.125 | 1.476 | 9 / 1200 |
  | baseline 2 | 1 | 0.928 | 2.117 | 1.137 | 1.399 | 7 / 1200 |
  | PR 2 | 1 | 0.843 | 2.326 | 1.083 | 1.321 | 4 / 1200 |

  All worst-cell means are within B. In these PR reruns, pooled p95/p99 are within 1.5 B at every budget, while the single worst call exceeds 1.5 B at all three budgets in at least one run. B = 16 max is 25.852 ms in PR run 1, above the 24 ms criterion; B = 5 max is 13.437 ms in PR run 1, above 7.5 ms. B = 1 max is 1.939 / 2.326 ms, the exception already allowed by the ticket. The quieter WSL baseline also has few outliers, so these runs do not establish a consistent worst-case advantage at B = 5; they support reporting frequency and percentiles alongside max instead of an unconditional timing claim. Raw samples are local `/tmp/53-equity-tail-{baseline,pr}-{1,2}.json`.

  Reproduce the summary from the repository root (four sequential fresh processes; redirect to a log when running in the background):

  ```bash
  for rev in 3868baf ce8cce9 3868baf ce8cce9; do
    .venv/bin/python - "$rev" <<'PY'
  import os, random, subprocess, sys, time, types
  from pathlib import Path
  import numpy as np
  rev = sys.argv[1]
  E = types.ModuleType("equity_benchmark")
  E.__file__ = str(Path("bot/equity.py").resolve())
  source = subprocess.check_output(["git", "show", f"{rev}:bot/equity.py"], text=True)
  exec(compile(source, E.__file__, "exec"), E.__dict__)
  assert E.tables_loaded()
  print(rev, "load_start", os.getloadavg(), flush=True)
  for budget in (16, 5, 1):
      spots, rng = random.Random(28), np.random.default_rng(28)
      cells = []
      for board_size in (3, 4, 5):
          for pct in (0.0, 0.5):
              timings = []
              for _ in range(200):
                  cards = spots.sample(range(36), 5 + board_size)
                  start = time.perf_counter()
                  value = E.equity(cards[:5], cards[5:], opp_min_pct=pct,
                                   time_budget_ms=budget, rng=rng)
                  timings.append((time.perf_counter() - start) * 1000)
                  assert 0 <= value <= 1
              cells.append(timings)
      pooled = np.array(cells).ravel()
      assert pooled.size == 6 * 200 == 1200
      print(budget, "worst_cell_mean", max(map(np.mean, cells)),
            "max", pooled.max(), "p95/p99", np.percentile(pooled, [95, 99]),
            "over_1.5B", int((pooled > 1.5 * budget).sum()), "/", pooled.size,
            flush=True)
  print("load_end", os.getloadavg(), flush=True)
  PY
  done > /tmp/53-equity-tail-summary.log 2>&1
  ```
- Reviewer reproduction: [Kyle's change request on PR #54](https://github.com/shaswat-singh23/datathon-poker/pull/54#issuecomment-6713447455), code `ce8cce9f84c3a17c7a2598ab43906a743fbd9df8`, alternating two PR and two baseline sweeps, load 7–8 on a 10-core Mac. At B = 16, PR maxima were **53.8 / 92.4 ms**, with **2 / 8 calls over 24 ms out of 1200**; p95 was 16.1 / 16.7 ms. Baseline maxima were 23.6 / 36.1 ms, with 0 / 2 outliers. At B = 5, PR outlier counts were 1 / 0 versus baseline 67 / 16. At B = 1, PR maxima were 2.8 / 9.4 ms with 80 / 70 outliers. The review did not report p99; the fresh sweeps above measure it directly. The earlier B = 16 maximum claim did not reproduce.
- Stall caveat, all budgets: a deadline check only decides whether to start the next batch. It cannot interrupt an in-flight batch or bound time while the process is descheduled. Python garbage collection can also add pauses. The reviewer attributes the 50–90 ms B = 16 spikes to preemption or GC; no scheduler/GC trace was captured to distinguish those causes. The same caveat applies at B = 5 and B = 1, where even a single batch and fixed setup can exceed 1.5 B. Percentiles and counts show how often this occurs; neither is a hard maximum guarantee. Thus the ticket's worst-call criterion is not consistently met on shared hosts, even when the mean and high percentiles are within the target.
- So what: the smaller batches reduce avoidable overruns and let postflop check the deadline more often. The original postflop sweep's worst 20 ms-budget call fell from 47.7 to 15.6 ms, but that observed maximum is not a bound on future decisions. The B = 5 outlier improvement reproduces in the review; rare long stalls at B = 16 remain. These measurements do not prove that a half cannot exhaust its time bank or reach the forfeit path.
- Verification after syncing with master `4464f11`: `.venv/bin/python -m pytest -q` **459 passed** (17.39 s; one dependency deprecation warning). The sandbox run hung in FastAPI's test client; rerunning outside the sandbox passed. All 12 new table rows were checked against the raw samples and all 14,400 calls counted; the embedded Python compiles, its shell wrapper passes `bash -n`, and `git diff --check` passes. `./tools/check_build.sh` could not complete: Docker is unavailable here (the script fails at `docker info`).
- Checked by: unchecked (revised findings await independent re-review)
