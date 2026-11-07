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
