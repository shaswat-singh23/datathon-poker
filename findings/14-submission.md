# Submission dry run
- Issue: #14 | Author: Shaswat (agent) | Time: 14:48
- Claim: commit `7a63b825a8d3637ed2e91b070e783d77ee676367` is a submit-ready candidate. It names the bot **The Conductors / ShortDeckShark**, passes the organizers' tests, and passes the organizers' smoke test against the live server. `./tools/check_build.sh` has **not** run on it yet, because there's no Docker on the machine that made it.
- Evidence:
  - Repo URL: https://github.com/shaswat-singh23/datathon-poker (made PUBLIC 2026-11-07 ~14:45 CST; first, every commit was scanned for `.env` files and API-key/token patterns, and none turned up)
  - Candidate SHA: `7a63b825a8d3637ed2e91b070e783d77ee676367` (agent.py `PARTICIPANT = "The Conductors"`, `AGENT_NAME = "ShortDeckShark"`)
  - `.venv/bin/python -m pytest -q` → 131 passed
  - `PORT=5047 .venv/bin/python agent.py` + `.venv/bin/python tools/smoke_test.py --port 5047 --startup 15` → SMOKE TEST PASSED (GET / answered after 0.8 s naming "The Conductors / ShortDeckShark", every sample /act legal in ≤ 4 ms)
  - `./tools/check_build.sh` → **not run** (`docker: command not found` in this WSL environment). This still needs someone with Docker.
- So what: the submission path works up to the Docker build: the names are set, the repo is public, and the bot answers the judge's protocol. The SHA above is a dry-run candidate, not the final pick. Strategy PRs that merge later need a new SHA in the form, and each new SHA needs its own check_build run.
- Checked by: unchecked

## Before submitting the form
1. On a machine with Docker, check out the SHA you'll submit and run `./tools/check_build.sh`. It must print `ALL CHECKS PASSED`.
2. Submit team name **The Conductors**, the repo URL above, and that full 40-char SHA.
3. If any later commit is submitted instead, record it here (or in a new findings file) with its check_build result.

## check_build results (#50)
- Issue: #50 | Author: Kyle (Claude Code) | Time: 2026-11-07 16:58 CST
- Claim: `./tools/check_build.sh` prints **ALL CHECKS PASSED** in Docker on both the dry-run candidate `7a63b825a8d3637ed2e91b070e783d77ee676367` and the current master `b9fa456a73f0d95f8deb521fc1543254aa2b44be` (36 commits later; `7a63b82` is an ancestor of it). Either is build-eligible for the form. Which one goes on the form is the final-SHA gate's call (#57), not this ticket's.
- Evidence: Kyle's Mac, Docker 29.6.2 (Docker Desktop; its credential helper must be on the PATH for the base image to build: `PATH="$PATH:/Applications/Docker.app/Contents/Resources/bin" ./tools/check_build.sh`; without it the build fails with `docker-credential-desktop: executable file not found`, which is the machine's fault, not the bot's). Each SHA was exported with `git archive` into its own clean directory and the script run from that directory's root, so only committed files took part, as in the real build. Both runs exited 0. Image size added on top of the base: 1 MB (cap 3072 MB). Output tails:

  `7a63b825a8d3637ed2e91b070e783d77ee676367`:
  ```
  ==> Starting your bot like the tournament does, then running the smoke test...
    ok  GET / answered after 0.8 s: The Conductors / ShortDeckShark
    ok  POST /new-half worked
    ok  /act preflop, button to act: CHECK_CALL in 1 ms
    ok  /act preflop, facing a pot raise: CHECK_CALL in 1 ms
    ok  /act flop, first to act: CHECK_CALL in 4 ms
    ok  /act flop, facing an all-in (only FOLD or CHECK_CALL): CHECK_CALL in 8 ms
    ok  /act river, facing a half-pot bet: CHECK_CALL in 4 ms
    ok  POST /hand-end worked
  SMOKE TEST PASSED

  ALL CHECKS PASSED. Commit and push, then submit your full commit SHA (git rev-parse HEAD).
  ```

  `b9fa456a73f0d95f8deb521fc1543254aa2b44be` (master at 16:58 CST):
  ```
  ==> Starting your bot like the tournament does, then running the smoke test...
    ok  GET / answered after 0.8 s: The Conductors / ShortDeckShark
    ok  POST /new-half worked
    ok  /act preflop, button to act: CHECK_CALL in 1 ms
    ok  /act preflop, facing a pot raise: CHECK_CALL in 1 ms
    ok  /act flop, first to act: CHECK_CALL in 2 ms
    ok  /act flop, facing an all-in (only FOLD or CHECK_CALL): CHECK_CALL in 4 ms
    ok  /act river, facing a half-pot bet: CHECK_CALL in 2 ms
    ok  POST /hand-end worked
  SMOKE TEST PASSED

  ALL CHECKS PASSED. Commit and push, then submit your full commit SHA (git rev-parse HEAD).
  ```
- So what: the one thing #14 could not do (no Docker there) is done, for the recorded candidate and for today's master. The form can be filed with either SHA as far as the build goes. Any SHA submitted later needs its own run of the command above; paste the tail into the table below.
- Checked by: unchecked

## Submission record
Filled in by whoever submits the organizers' form. One row per submission or resubmission. A SHA goes in this table only after `check_build` passed on it (above or in a later findings file) and, for a resubmission, after the final-SHA gate (#57) said SUBMIT.

| # | time (Central) | submitted by | SHA on the form | check_build | gate (#57) |
|---|---|---|---|---|---|
| 1 | 2026-11-07 21:31 | Shaswat | `f203491f5c4266fdd285738cf32669c123cc1bba` | "passed" per Shaswat's #50 comment; no output recorded (note 1) | not gated: #78 says SUBMIT `05c1a8ec…`, not this SHA (note 2) |

Notes on row 1. Source: Shaswat's comment on #50, 2026-11-07 21:31 CT: "Form filed 21:31 CT by Shaswat: The Conductors, f203491f5c4266fdd285738cf32669c123cc1bba." The time is when that comment says the form was filed.
1. **check_build.** The only record is that comment ("check_build passed"). No output tail is pasted on #50, and no findings file has a run on `f203491`.
2. **Gate.** The merged #78 gate (`findings/78-final-gate-2.md`) measured `05c1a8ecadbb1186c94a670796905fff9d73fc8c` and says SUBMIT that SHA. It names `f203491` only to say master had moved past it before the gate started. The comment's "34.5/36 @8s, 36.0/36 @4s vs 7a63b82's 24.5/18.0" matches neither table in that finding.
3. **Open on #50.** The orchestrator asked (21:31 CST) that the form and the finding name the same SHA: re-file with `05c1a8e` and run check_build on it, or post which run produced the 34.5/36 numbers and its log path. When that is settled, add a row 2 below instead of editing row 1.

Deadline (Central time): _to be pinned by the decider in AGENTS.md and on #50_.
