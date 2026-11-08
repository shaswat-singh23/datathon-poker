# Final SHA gate 2: master `05c1a8e` vs the form's `7a63b82`. Decision: SUBMIT `05c1a8e`
- Issue: #78 | Author: Kyle (Claude Code, orchestrator worker) | Time: 21:01
- Claim: master `05c1a8ecadbb1186c94a670796905fff9d73fc8c` (`05c1a8e Merge pull request #80 from shaswat-singh23/77-wider-field`) beats the SHA on the form, `7a63b825a8d3637ed2e91b070e783d77ee676367`, on the 15-bot field. On the quiet pass (pass 2) it scores **42.5 vs 30.0 / 45 at 8 s** and **43.0 vs 21.5 / 45 at 4 s** (mean +3.47 vs +2.60 and +3.51 vs +0.76 bb/deal). It loses no match at either bank (W-L-C 40-0-5 and 41-0-4). Safety is all zero for both SHAs in all 8 gate runs. The candidate's slowest decision in CPU time was 16.0 ms. `./tools/check_build.sh` prints ALL CHECKS PASSED in Docker on a clean `git archive` of `05c1a8e`.
- Evidence: `tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --procs 3 --time-bank {4,8}`, 3 seeds × 1000 deals, duplicate format, default seed base `sim` (same seeds for every run), 15-bot field (4 baseline + 11 sparring), **45 matches per row**. Two full passes of the four runs, one run at a time. JSON in `data/78-{05c1a8e,7a63b82}-tb{4,8}{,-r2}.json` (main clone, gitignored).
- So what: the form holds a bot that scores 21.5 / 45 when its CPU budget shrinks and 30 / 45 at the real bank. Master scores 42.5 to 43 at both. This is the SHA to put on the form.
- Checked by: unchecked

## Which SHA was gated, and why not the ticket's `f203491`
- The ticket named master `f203491`. By the time this worker started (20:29), master had moved to `05c1a8e` (merged #77's wider sparring field and #64's exploit import), so the current master was gated instead.
- **`a4eafee` (PR #83, #82 cbetter gate) landed on master at 20:31, mid-gate, and was NOT gated.** The decision line names `05c1a8e` exactly. Submitting `a4eafee` or anything later needs its own gate.

## How the runs were made
- **Candidate** `05c1a8e`: this worktree, its own `tools/sim.py` and `tools/opponents/`.
- **Form** `7a63b82`: a detached worktree at `/tmp/gate78-7a63b82` (removed afterwards). I copied the candidate's `tools/sim.py` over that checkout's sim, and **replaced its `tools/opponents/` with the candidate's** (the form SHA had 8 sparring bots; master has 11, adding cbetter, fitorfold and honest). Both copies were uncommitted. So both SHAs faced the same 15 opponents with the same sim. `game.py`, `evaluator.py`, `judge_engine.py` and `baseline-bots/` are byte-identical between the two SHAs. I did not run `--hero /tmp/.../agent.py` from the candidate checkout (its `sys.path` would import the candidate's `bot/`).
- Each run waited for a 1-min load of 12 or less before starting (pass 2 also waited until no `gate/new` process was running). Load was sampled every 15 s.
- The field glob expanded: every log reads `Hero agent vs 15 opponents x 3 seeds x 1000 deals, 3 procs`. (The earlier `/Users/kyledong/gate/*.log` attempt ran "vs 2 opponents" and is not used.)

## Gate table (hero = the SHA; 45 matches per row; safety over 90 hero halves)

| pass | SHA | bank | points | W-L-C | mean bb/deal [95% CI] | max decision wall / CPU ms | halves > 100 ms wall / CPU | max half think | errors / forfeits / bank-empties |
|---|---|---|---|---|---|---|---|---|---|
| 2 | `7a63b82` (form) | 8 s | **30.0 / 45** | 25-10-10 | +2.596 [+2.440, +2.751] | 140.9 / 26.6 | 3 / 0 | 4.66 s | 0 / 0 / 0 |
| 2 | `05c1a8e` (master) | 8 s | **42.5 / 45** | 40-0-5 | +3.467 [+3.312, +3.623] | 381.0 / 16.0 | 3 / 0 | 5.95 s | 0 / 0 / 0 |
| 2 | `7a63b82` (form) | 4 s | **21.5 / 45** | 17-19-9 | +0.764 [+0.601, +0.927] | 230.3 / 20.9 | 3 / 0 | 1.23 s | 0 / 0 / 0 |
| 2 | `05c1a8e` (master) | 4 s | **43.0 / 45** | 41-0-4 | +3.513 [+3.358, +3.669] | 62.1 / 10.6 | 0 / 0 | 2.93 s | 0 / 0 / 0 |
| 1 | `7a63b82` (form) | 8 s | **27.5 / 45** | 20-10-15 | +2.335 [+2.177, +2.492] | 437.7 / 34.0 | 41 / 0 | 5.54 s | 0 / 0 / 0 |
| 1 | `05c1a8e` (master) | 8 s | **42.5 / 45** | 40-0-5 | +3.525 [+3.370, +3.680] | 184.4 / 11.0 | 3 / 0 | 5.89 s | 0 / 0 / 0 |
| 1 | `7a63b82` (form) | 4 s | **21.5 / 45** | 17-19-9 | +0.718 [+0.555, +0.880] | 137.5 / 26.2 | 2 / 0 | 1.37 s | 0 / 0 / 0 |
| 1 | `05c1a8e` (master) | 4 s | **41.5 / 45** | 38-0-7 | +3.526 [+3.371, +3.682] | 129.4 / 10.6 | 3 / 0 | 2.96 s | 0 / 0 / 0 |

Opponents had 0 errors and 0 bank empties in every run.

## bb/deal per opponent [95% CI], W-L-C = points (pass 2)

| opponent | form 8 s | master 8 s | form 4 s | master 4 s |
|---|---|---|---|---|
| baseline_calling_station | +8.944 [+8.417, +9.472] 3-0-0 = 3 | +10.139 [+9.599, +10.679] 3-0-0 = 3 | +8.063 [+7.560, +8.566] 3-0-0 = 3 | +10.114 [+9.575, +10.652] 3-0-0 = 3 |
| baseline_always_half | +9.276 [+8.427, +10.124] 3-0-0 = 3 | +9.254 [+8.402, +10.106] 3-0-0 = 3 | +7.064 [+6.271, +7.857] 3-0-0 = 3 | +9.276 [+8.423, +10.129] 3-0-0 = 3 |
| maniac | +6.606 [+5.644, +7.569] 3-0-0 = 3 | +5.795 [+4.831, +6.760] 3-0-0 = 3 | +4.559 [+3.605, +5.513] 3-0-0 = 3 | +5.984 [+5.015, +6.953] 3-0-0 = 3 |
| baseline_random | +5.822 [+5.069, +6.574] 3-0-0 = 3 | +5.721 [+4.918, +6.525] 3-0-0 = 3 | +5.780 [+4.973, +6.587] 3-0-0 = 3 | +5.992 [+5.194, +6.791] 3-0-0 = 3 |
| baseline_always_pot | +6.049 [+5.086, +7.012] 3-0-0 = 3 | +5.540 [+4.568, +6.513] 3-0-0 = 3 | +4.791 [+3.830, +5.752] 3-0-0 = 3 | +5.552 [+4.580, +6.525] 3-0-0 = 3 |
| lag | +4.316 [+3.730, +4.901] 3-0-0 = 3 | +4.382 [+3.747, +5.017] 3-0-0 = 3 | −0.394 [−1.043, +0.256] 0-0-3 = 1.5 | +4.539 [+3.898, +5.181] 3-0-0 = 3 |
| potodds | +1.305 [+0.926, +1.684] 3-0-0 = 3 | +3.768 [+3.283, +4.253] 3-0-0 = 3 | −3.939 [−4.438, −3.441] 0-3-0 = 0 | +3.758 [+3.276, +4.240] 3-0-0 = 3 |
| honest | +1.098 [+0.703, +1.493] 2-0-1 = 2.5 | +2.792 [+2.319, +3.265] 3-0-0 = 3 | −4.353 [−4.912, −3.794] 0-3-0 = 0 | +2.635 [+2.175, +3.094] 3-0-0 = 3 |
| exploiter | −1.425 [−1.859, −0.991] 0-3-0 = 0 | +1.083 [+0.714, +1.452] 3-0-0 = 3 | −3.483 [−3.981, −2.985] 0-3-0 = 0 | +1.091 [+0.724, +1.458] 3-0-0 = 3 |
| fitorfold | −1.631 [−2.050, −1.211] 0-3-0 = 0 | +0.912 [+0.612, +1.212] 3-0-0 = 3 | −2.576 [−3.044, −2.109] 0-3-0 = 0 | +0.977 [+0.671, +1.284] 3-0-0 = 3 |
| nit | −0.456 [−0.774, −0.139] 0-1-2 = 1 | +0.900 [+0.694, +1.105] 3-0-0 = 3 | −0.365 [−0.689, −0.042] 0-1-2 = 1 | +1.014 [+0.807, +1.220] 3-0-0 = 3 |
| tag | −1.831 [−2.230, −1.431] 0-3-0 = 0 | +0.774 [+0.476, +1.072] 3-0-0 = 3 | −2.972 [−3.422, −2.522] 0-3-0 = 0 | +0.832 [+0.528, +1.136] 3-0-0 = 3 |
| trappy | +0.308 [+0.048, +0.568] 0-0-3 = 1.5 | +0.560 [+0.270, +0.849] 2-0-1 = 2.5 | −0.574 [−0.868, −0.280] 0-2-1 = 0.5 | +0.549 [+0.258, +0.839] 3-0-0 = 3 |
| rock_shover | +0.735 [+0.368, +1.101] 2-0-1 = 2.5 | +0.549 [+0.320, +0.779] 2-0-1 = 2.5 | +0.771 [+0.403, +1.139] 2-0-1 = 2.5 | +0.525 [+0.291, +0.760] 2-0-1 = 2.5 |
| cbetter | −0.180 [−0.732, +0.373] 0-0-3 = 1.5 | −0.159 [−0.745, +0.426] 0-0-3 = 1.5 | −0.914 [−1.476, −0.352] 0-1-2 = 1 | −0.136 [−0.717, +0.446] 0-0-3 = 1.5 |

Pass 1 per-opponent points match pass 2 except: form 8 s potodds 1.5 (pass 2: 3) and honest 1.5 (2.5); master 4 s exploiter, tag, trappy 2.5 each (3). Master 8 s and form 4 s are identical per opponent across passes. Pass-1 bb/deal per opponent is in the JSON.

Only cbetter holds master to chops (3 chops at both banks, −0.16 / −0.14 bb/deal, CI straddles 0). That is #82's subject (merged as `a4eafee`, not gated here).

## Load (1-min load average, sampled every 15 s)

| pass | run | start | before | peak | samples > 15 | after |
|---|---|---|---|---|---|---|
| 1 | master 4 s | 20:32:58 | 10.39 | 20.75 | 4 / 11 | 18.10 |
| 1 | form 4 s | 20:36:43 | 11.20 | 11.20 | 0 / 6 | 8.23 |
| 1 | master 8 s | 20:38:13 | 8.23 | 10.64 | 0 / 16 | 4.98 |
| 1 | form 8 s | 20:42:13 | 4.98 | **92.32** | 15 / 18 | 81.18 |
| 2 | master 4 s | 20:49:14 | 10.81 | 10.81 | 0 / 11 | 6.11 |
| 2 | form 4 s | 20:51:59 | 6.11 | 7.11 | 0 / 5 | 6.70 |
| 2 | master 8 s | 20:53:14 | 6.70 | 6.70 | 0 / 16 | 5.91 |
| 2 | form 8 s | 20:57:14 | 5.91 | 7.11 | 0 / 14 | 6.05 |

**Pass 1 is invalid for timing.** Its master 4 s run overlapped a merge-queue sim (peak 20.75), and its form 8 s run overlapped a foreign 9-proc gate run (a Codex session gating `f203491` from `~/gate/new`). The coordinator saw load reach 58; my samples peaked at 92. That run's 41 wall-time halves over 100 ms are this load. Pass 2 never went above 10.81 and is the basis of the decision. **Pass 1 agrees with pass 2 on points**: master leads by 15.0 at 8 s (42.5 vs 27.5) and 20.0 at 4 s (41.5 vs 21.5).

### Aborted first attempt (not a gate row, disclosed for safety)
A first master 4 s run (20:29:30) failed only at the end, when writing its JSON, because `data/` did not exist in the main clone. It overlapped the merge-queue sim (load to 31). In it, master had **2 errors**, both vs cbetter (seeds sim-0 and sim-2, one in each half 1): a single decision took **1053.9 ms wall** with a CPU max of only 11.0 ms. The process was descheduled past the 1 s per-decision limit, not slow code. 2 errors in a half is far from the 5 needed to forfeit, and no gate run (load ≤ 92) repeated it. The candidate's CPU max over all 8 gate runs is 16.0 ms. It is still a reminder that the real judge's 1 s limit is wall time. Log: `/tmp/78-05c1a8e-tb4-aborted.log` (local).

## Gate rule applied (#57's rule)
Rule: ship only if points at both banks ≥ the form SHA's, safety is all zero, and the max decision is under 100 ms in CPU time.
- **Points, 8 s:** 42.5 ≥ 30.0 (pass 2), 42.5 ≥ 27.5 (pass 1). Pass.
- **Points, 4 s:** 43.0 ≥ 21.5 (pass 2), 41.5 ≥ 21.5 (pass 1). Pass.
- **Safety:** 0 errors, 0 forfeits and 0 bank empties for both SHAs in all 8 gate runs. Pass. The candidate's max half think was 5.95 s of 8 and 2.96 s of 4: #46/#48's timing spending the bank on purpose and keeping the reserve.
- **Max decision under 100 ms (CPU):** candidate 16.0 ms max, and no half had a CPU decision over 100 ms. Pass. Wall-time maxima over 100 ms (up to 381.0 ms, on the quiet pass 2 too, at load ≤ 6.7) appear for both SHAs with CPU ≤ 26.6 ms. That is OS scheduling on this Mac, as #57 found.

The rule holds on **every pass** (both pass 1 and pass 2), with margins of 12.5 to 21.5 points.

**Decision: SUBMIT `05c1a8ecadbb1186c94a670796905fff9d73fc8c`.**

## check_build on the chosen SHA
`05c1a8e` exported with `git archive` into a clean directory, then `PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH" ./tools/check_build.sh` from its root. Exit 0:
```
==> Checking the size...
    your bot adds 1 MB on top of the base (cap: 3072 MB)

==> Starting your bot like the tournament does, then running the smoke test...
  ok  GET / answered after 0.8 s: The Conductors / ShortDeckShark
  ok  POST /new-half worked
  ok  /act preflop, button to act: CHECK_CALL in 1 ms
  ok  /act preflop, facing a pot raise: CHECK_CALL in 1 ms
  ok  /act flop, first to act: RAISE_HALF in 3 ms
  ok  /act flop, facing an all-in (only FOLD or CHECK_CALL): CHECK_CALL in 14 ms
  ok  /act river, facing a half-pot bet: CHECK_CALL in 1 ms
  ok  POST /hand-end worked
SMOKE TEST PASSED

ALL CHECKS PASSED. Commit and push, then submit your full commit SHA (git rev-parse HEAD).
```

## Next step (human)
Updating the form is a human step. This ticket did not touch the form or `findings/14-submission.md`. The SHA and gate table are posted on #50.
