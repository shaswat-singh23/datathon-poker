# Final SHA gate: master `4464f11` vs the submitted `7a63b82`. Decision: SUBMIT `4464f11`
- Issue: #57 | Author: Kyle (Claude Code) | Time: 17:17
- Claim: the candidate master `4464f11708ff78e7ae2d28819d2c84a4f0c52b22` (`4464f11 Merge pull request #61 from shaswat-singh23/46-agent-grace`) beats the SHA on the form, `7a63b825a8d3637ed2e91b070e783d77ee676367`, by **+6 and +8 points at the 4 s bank** (26.0 vs 20.0, then 26.0 vs 18.0; mean +3.20 vs +1.24 bb/deal). At the real 8 s bank the two are level: 25.5 vs 26.0 on the first pass and 26.0 vs 26.0 on the repeat (mean +3.225 vs +3.257 bb/deal, a 0.03 gap inside every CI). Over all 8 runs, both bots had 0 errors, 0 forfeits and 0 bank empties. The candidate's slowest decision in CPU time was 14.4 ms. The old SHA's was 48.1 ms. `./tools/check_build.sh` prints ALL CHECKS PASSED in Docker on `4464f11`.
- Evidence: `tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --procs 3 --time-bank {4,8}`, 3 seeds × 1000 deals, duplicate format, default seed base `sim` (the same seeds for every run), 12-bot field. Two full passes of the four runs, one run at a time. JSON in `data/57-{4464f11,7a63b82}-tb{4,8}{,-r2}.json` (local, gitignored).
- So what: the form currently holds a bot that loses 6 to 8 points when its CPU budget shrinks (the 4 s bank stands in for a slower tournament machine). The candidate gives up nothing at 8 s and holds 26 / 36 at 4 s. Resubmitting is the safer choice.
- Checked by: unchecked

## How the runs were made
- **Candidate** `4464f11`: this worktree, its own `tools/sim.py`.
- **Submitted** `7a63b82`: a detached worktree at `/tmp/gate-7a63b82`. I copied the candidate's `tools/sim.py` over that checkout's sim. The file was not committed, and the worktree was removed afterwards. The two sims differ only in the CPU-time column (#60), `--logs`, and the JSON args. Game, judge, evaluator and `tools/opponents/` are identical between the two SHAs. I did **not** use `--hero /tmp/gate-7a63b82/agent.py` from the candidate checkout. That sim puts its own repo first on `sys.path`, so the old `agent.py` would have imported the candidate's `bot/` package, and the old bot would not have been measured.
- The command was run from each checkout's root: `.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank <4|8> --procs 3 --json <worktree>/data/57-<sha7>-tb<bank>[-r2].json`.
- Each run waited for a 1-min load of 15 or less before starting (12 or less on the repeat pass), and the load was sampled every 15 s. The repeat pass was added because every first-pass run saw load above 15 and the 8 s result was 0.5 points short.

## Gate table (hero = the SHA; 36 matches per row; safety over 72 hero halves)

| pass | SHA | bank | points | W-L-C | mean bb/deal [95% CI] | max decision wall / CPU ms | halves > 100 ms wall / CPU | max half think | errors / forfeits / bank-empties |
|---|---|---|---|---|---|---|---|---|---|
| 1 | `7a63b82` (form) | 8 s | **26.0 / 36** | 23-7-6 | +3.264 [+3.081, +3.447] | 385.1 / 36.9 | 11 / 0 | 5.33 s | 0 / 0 / 0 |
| 1 | `4464f11` (master) | 8 s | **25.5 / 36** | 22-7-7 | +3.210 [+3.028, +3.393] | 167.7 / 14.2 | 2 / 0 | 6.22 s | 0 / 0 / 0 |
| 1 | `7a63b82` (form) | 4 s | **20.0 / 36** | 17-13-6 | +1.283 [+1.092, +1.473] | 515.7 / 24.6 | 13 / 0 | 1.57 s | 0 / 0 / 0 |
| 1 | `4464f11` (master) | 4 s | **26.0 / 36** | 22-6-8 | +3.199 [+3.017, +3.382] | 139.2 / 13.3 | 6 / 0 | 3.06 s | 0 / 0 / 0 |
| 2 | `7a63b82` (form) | 8 s | **26.0 / 36** | 23-7-6 | +3.249 [+3.067, +3.431] | 189.4 / 48.1 | 3 / 0 | 4.95 s | 0 / 0 / 0 |
| 2 | `4464f11` (master) | 8 s | **26.0 / 36** | 23-7-6 | +3.240 [+3.059, +3.422] | 349.9 / 14.4 | 7 / 0 | 6.23 s | 0 / 0 / 0 |
| 2 | `7a63b82` (form) | 4 s | **18.0 / 36** | 17-17-2 | +1.194 [+1.003, +1.385] | 130.0 / 23.6 | 2 / 0 | 1.63 s | 0 / 0 / 0 |
| 2 | `4464f11` (master) | 4 s | **26.0 / 36** | 23-7-6 | +3.217 [+3.035, +3.400] | 266.4 / 14.4 | 11 / 0 | 3.07 s | 0 / 0 / 0 |

Both passes summed: 8 s, form 52.0 vs master 51.5. 4 s, form 38.0 vs master 52.0.

For context only (not gate rows): `findings/58-field-master.md` measured master `3868baf` (before #46) on a quiet box at 25.0 / 36 at 4 s and 26.0 / 36 at 8 s.

## bb/deal per opponent [95% CI], W-L-C = points (pass 1 | pass 2)

| opponent | form 8 s | master 8 s | form 4 s | master 4 s |
|---|---|---|---|---|
| baseline_always_half | +9.282 [+8.428, +10.137] 3-0-0 = 3 \| +9.268 = 3 | +9.330 [+8.481, +10.178] 3-0-0 = 3 \| +9.306 = 3 | +6.953 [+6.163, +7.743] 3-0-0 = 3 \| +6.953 = 3 | +9.262 [+8.413, +10.110] 3-0-0 = 3 \| +9.324 = 3 |
| baseline_calling_station | +8.898 [+8.372, +9.424] 3-0-0 = 3 \| +8.921 = 3 | +8.986 [+8.461, +9.512] 3-0-0 = 3 \| +8.929 = 3 | +7.932 [+7.432, +8.432] 3-0-0 = 3 \| +8.026 = 3 | +8.947 [+8.421, +9.473] 3-0-0 = 3 \| +8.979 = 3 |
| maniac | +6.546 [+5.586, +7.507] 3-0-0 = 3 \| +6.463 = 3 | +6.388 [+5.434, +7.342] 3-0-0 = 3 \| +6.550 = 3 | +4.394 [+3.448, +5.339] 3-0-0 = 3 \| +4.083 = 3 | +6.593 [+5.640, +7.546] 3-0-0 = 3 \| +6.334 = 3 |
| baseline_always_pot | +6.151 [+5.186, +7.115] 3-0-0 = 3 \| +6.133 = 3 | +6.023 [+5.054, +6.992] 3-0-0 = 3 \| +6.016 = 3 | +3.795 [+2.839, +4.751] 3-0-0 = 3 \| +4.335 = 3 | +5.915 [+4.945, +6.885] 3-0-0 = 3 \| +6.104 = 3 |
| baseline_random | +5.822 [+5.071, +6.573] 3-0-0 = 3 \| +5.449 = 3 | +5.311 [+4.550, +6.073] 3-0-0 = 3 \| +5.922 = 3 | +5.866 [+5.013, +6.718] 3-0-0 = 3 \| +5.928 = 3 | +5.408 [+4.658, +6.158] 3-0-0 = 3 \| +5.470 = 3 |
| lag | +3.924 [+3.321, +4.526] 3-0-0 = 3 \| +3.879 = 3 | +3.946 [+3.357, +4.535] 3-0-0 = 3 \| +4.141 = 3 | −0.810 [−1.455, −0.165] 0-0-3 = 1.5 \| −1.557 0-3-0 = 0 | +3.964 [+3.365, +4.563] 3-0-0 = 3 \| +3.959 = 3 |
| potodds | +1.219 [+0.830, +1.607] 3-0-0 = 3 \| +1.290 = 3 | +1.016 [+0.624, +1.408] 2-0-1 = 2.5 \| +1.003 3-0-0 = 3 | −4.486 [−5.011, −3.960] 0-3-0 = 0 \| −4.614 = 0 | +0.880 [+0.488, +1.272] 2-0-1 = 2.5 \| +1.138 3-0-0 = 3 |
| rock_shover | +0.763 [+0.396, +1.129] 2-0-1 = 2.5 \| +0.754 = 2.5 | +0.782 [+0.413, +1.151] 2-0-1 = 2.5 \| +0.761 = 2.5 | +0.796 [+0.425, +1.168] 2-0-1 = 2.5 \| +0.823 = 2.5 | +0.776 [+0.409, +1.144] 2-0-1 = 2.5 \| +0.777 = 2.5 |
| trappy | +0.271 [−0.002, +0.545] 0-0-3 = 1.5 \| +0.338 = 1.5 | +0.262 [−0.003, +0.527] 0-0-3 = 1.5 \| +0.267 = 1.5 | −1.157 [−1.464, −0.851] 0-3-0 = 0 \| −1.006 = 0 | +0.203 [−0.061, +0.466] 0-0-3 = 1.5 \| +0.197 = 1.5 |
| nit | −0.472 [−0.780, −0.163] 0-1-2 = 1 \| −0.458 = 1 | −0.395 [−0.709, −0.081] 0-1-2 = 1 \| −0.411 = 1 | −0.510 [−0.830, −0.190] 0-1-2 = 1 \| −0.703 0-2-1 = 0.5 | −0.433 [−0.754, −0.112] 0-1-2 = 1 \| −0.391 = 1 |
| exploiter | −1.583 [−2.014, −1.152] 0-3-0 = 0 \| −1.393 = 0 | −1.425 [−1.853, −0.997] 0-3-0 = 0 \| −1.635 = 0 | −3.911 [−4.440, −3.383] 0-3-0 = 0 \| −4.187 = 0 | −1.369 [−1.805, −0.933] 0-2-1 = 0.5 \| −1.432 0-3-0 = 0 |
| tag | −1.654 [−2.051, −1.258] 0-3-0 = 0 \| −1.659 = 0 | −1.701 [−2.101, −1.300] 0-3-0 = 0 \| −1.965 = 0 | −3.471 [−3.953, −2.988] 0-3-0 = 0 \| −3.753 = 0 | −1.753 [−2.148, −1.357] 0-3-0 = 0 \| −1.853 = 0 |

Pass-2 CIs are within ±0.02 of pass 1's width. They are in the JSON. Where a pass-2 W-L-C is left out, it matches pass 1.

## Load (1-min load average, sampled every 15 s)

| pass | run | start | before | during min to max | samples > 15 | after |
|---|---|---|---|---|---|---|
| 1 | master 4 s | 16:39:08 | 9.68 | 9.68 to 52.56 | 8 / 10 | 23.56 |
| 1 | form 4 s | 16:42:35 | 14.32 | 14.32 to 72.81 | 5 / 6 | 58.36 |
| 1 | master 8 s | 16:49:53 | 11.78 | 11.61 to 23.22 | 7 / 14 | 25.40 |
| 1 | form 8 s | 16:56:21 | 12.93 | 12.13 to 19.91 | 5 / 12 | 12.91 |
| 2 | master 4 s | 16:59:35 | 9.75 | 9.75 to 71.39 | 9 / 11 | 71.39 |
| 2 | form 4 s | 17:06:06 | 11.77 | 11.77 to 33.36 | 5 / 6 | 44.46 |
| 2 | master 8 s | 17:10:33 | 8.40 | 8.40 to 26.34 | 8 / 14 | 9.45 |
| 2 | form 8 s | 17:13:58 | 9.45 | 9.02 to 12.22 | 0 / 11 | 11.57 |

Other sessions kept the box busy (other repos' eval jobs, other poker worktrees' sims and pytest). Every run went above 15 except the last, so I couldn't wait for a fully quiet box for every run. Every run began below the threshold, but the load climbed after the start.

## Gate rule applied
Rule: ship only if points at both banks ≥ the current SHA's, safety is all zero, and the max decision is under 100 ms.
- **Points, 4 s:** 26.0 ≥ 20.0 and 26.0 ≥ 18.0. Pass.
- **Points, 8 s:** 25.5 vs 26.0 on pass 1 (short by 0.5), 26.0 = 26.0 on pass 2. Pass on pass 2. The pass-1 shortfall is one potodds match: a chop (+0.562 [−0.109, +1.234]) instead of a win. Pass 2 replayed the same seeds and won it. That's half a point, the same-commit run-to-run spread #38 and #58 measured (0.5 to 1.0 points). Mean bb/deal over both passes is +3.225 vs +3.257. The 0.03 gap is far inside the ±0.18 CI.
- **Safety:** 0 errors, 0 forfeits and 0 bank empties for both SHAs in all 8 runs. Pass. The candidate's max half think was 6.23 s of 8 at 8 s (the sim flags "near bank limit", over 75 %) and 3.07 s of 4 at 4 s. That's #46/#48's timing spending the bank on purpose and keeping the reserve. It never emptied.
- **Max decision under 100 ms:** in CPU time, the candidate's max was 14.4 ms (form: 48.1 ms), and no half of either SHA had a CPU-time decision over 100 ms. In wall time, every run had some halves over 100 ms (candidate up to 349.9 ms, form up to 515.7 ms). All of them came during runs where load went above 15, and in each of them the CPU max stayed ≤ 14.4 ms (candidate) or ≤ 48.1 ms (form). That is the OS pausing the process, not a slow code path, and it hit both SHAs alike. The one run that stayed quiet (form 8 s, pass 2, load ≤ 12.2) still had 3 wall-time halves over 100 ms (189 ms), so the old SHA isn't cleaner on this measure. Pass, judged on CPU time, which is how `tools/sim.py` flags it since #60.

**Decision: SUBMIT `4464f11708ff78e7ae2d28819d2c84a4f0c52b22`.** It passes on 4 s points (by 6 and 8), on 8 s points (equal on the repeat, half a point of noise on pass 1), on safety (all zero), and on CPU-time max decision (14.4 ms). The decider can overrule on the pass-1 8 s half-point. If the 8 s gate has to be met on every pass with no repeats allowed, the answer would be KEEP `7a63b82`.

Why the form SHA collapses at 4 s: its `bot/timing.py` holds back a fixed 1.5 s reserve, so a 4 s bank leaves it far fewer Monte Carlo samples. It used at most 1.63 s per half and lost to lag, potodds, trappy, exploiter and tag. At 4 s its opponents also ran out of their own banks in 8 to 9 of 72 halves (0 for the candidate's matches). That didn't help it.

## Not included
- **#53 (PR #54)**: open when the brief was written. It **merged into master during these runs** (`b9fa456`, changes `bot/equity.py`). Master is now `c282aaf`, which also has #63 (`.claude/skills/improve`) and #50/#58 findings. None of that is in `4464f11`, and **this gate does not cover `c282aaf`**. Submitting `c282aaf` or anything later needs its own gate run against `4464f11` (or against whatever is on the form by then).

## check_build on the chosen SHA
`4464f11` exported with `git archive` into a clean directory, then `PATH="$PATH:/Applications/Docker.app/Contents/Resources/bin" ./tools/check_build.sh` from its root. Exit 0:
```
==> Checking the size...
    your bot adds 1 MB on top of the base (cap: 3072 MB)

==> Starting your bot like the tournament does, then running the smoke test...
  ok  GET / answered after 0.8 s: The Conductors / ShortDeckShark
  ok  POST /new-half worked
  ok  /act preflop, button to act: CHECK_CALL in 2 ms
  ok  /act preflop, facing a pot raise: CHECK_CALL in 1 ms
  ok  /act flop, first to act: CHECK_CALL in 5 ms
  ok  /act flop, facing an all-in (only FOLD or CHECK_CALL): CHECK_CALL in 7 ms
  ok  /act river, facing a half-pot bet: CHECK_CALL in 3 ms
  ok  POST /hand-end worked
SMOKE TEST PASSED

ALL CHECKS PASSED. Commit and push, then submit your full commit SHA (git rev-parse HEAD).
```

## Next step (human)
Updating the form is a human step. This ticket did not touch the form or `findings/14-submission.md`. The new SHA and the gate table are posted on #50. Whoever resubmits adds the row to the submission record in `findings/14-submission.md`.
