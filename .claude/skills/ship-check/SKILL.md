---
name: ship-check
description: Pre-submission check that the repo, README, demo, and submission are ready. Use before submitting or when the user asks whether we are ready to ship.
model: sonnet
disable-model-invocation: true
---

Read AGENTS.md for the challenge's deliverables and judging weights. Run every check below. Report pass or fail for each, fix what you can, then re-check.

## Repo
- [ ] Fresh clone works: clone master into a temp dir and follow SETUP.md and the README run steps exactly. Report any error.
- [ ] Nothing in data/raw, no `.env` or keys, no file over 50 MB is tracked (`git ls-files` plus sizes). Search tracked files for strings that look like API keys.
- [ ] master has everyone's latest work merged. No open PRs with work we need.
- [ ] Every `must` issue is closed or deliberately dropped (`gh issue list --state open --label must`).

## Deliverable
- [ ] Every deliverable listed in AGENTS.md exists and works.
- [ ] Whatever is demoed (app, agent, server, notebook) starts from the fresh clone with no errors in its output.
- [ ] Nothing depends on a teammate's local path or local-only file.
- [ ] Deployed URL, if any, loads.

## README (judges read this)
- [ ] Opening paragraph: problem, what we built, the key result with a number.
- [ ] Data or inputs used, and how they were combined.
- [ ] Setup and run steps, verified by the fresh-clone check above.
- [ ] 2 or 3 example use cases.
- [ ] Every number matches a file in `findings/` that has been checked by someone other than its author.
- [ ] Images render.

## Submission
- [ ] Video is under the time limit, shows the thing working, and states the key result in the first 20 seconds.
- [ ] Devpost: all teammates added, correct challenges selected, repo link public or shared with judges.

Finish with the 3 riskiest remaining issues.
