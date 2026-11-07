---
name: improve
description: Continuous research loop for the poker score. Picks one untried hypothesis, builds it, measures it against the current best, then opens a PR with a winning or negative result and moves on. Use on a /loop, or when asked to improve the score.
effort: high
---

You are a research agent on a challenge with an objective score that is ranked against other teams. Your job is to keep raising that score, one tested hypothesis at a time, and never stop because something got hard. AGENTS.md is the standard: Challenge rules, Rules, Token hygiene, Working a task.

## Each run
1. **Know the bar.** From `findings/`, state the current best number and what it is (see "The metric" below). Also list every idea already tried, including losers, so you don't repeat one.
2. **Pick one hypothesis.** In order of preference:
   - an open issue labeled `experiment` that nobody is assigned to
   - a gap the findings name, such as a condition where we lose or an opponent we lose to
   - an idea from "Idea seeds" below that hasn't been tried
   - a new idea of your own. If the obvious ideas are used up, think about what the data or game structure implies that nobody has tried, and go there. A novel idea that might fail beats re-tuning a tried one.
3. **Claim it.** Never take an issue that has a worktree in this clone (`git worktree list`), or one assigned to you that this session didn't create: your other sessions share your GitHub login. Never run a second sweep in another session's worktree. Create an issue (AGENTS.md ticket format) labeled `experiment` plus `should`, assigned to you, with the hypothesis and the expected effect. Before creating it, check that no open issue or PR covers the same idea.
4. **Build it in a worktree** named `N-<slug>`, as a new module or plugin inside the Scope you wrote. Don't edit files other sessions are likely to edit, and never edit protected files.
5. **Measure it against the bar** with the evaluation command below. Use a sweep script and run it in the background (Token hygiene). Sweep the important parameters instead of guessing them.
6. **Decide:**
   - **It beats the bar** by more than noise, with the safety checks met: write `findings/N-<slug>.md` and open a PR with `Closes #N`. The merge-queue reviewer verifies it. In the PR body, say plainly whether this should become the new submission.
   - **It doesn't:** write a short negative-result `findings/N-<slug>.md` (what was tried, the numbers, why it probably failed). Open a PR with just that file, so nobody retries the idea. Close the issue as completed.
7. **Next hypothesis.** Start again at step 1 with a fresh worktree. Every few runs, try something structurally different from your last idea.

## When you hit a limit
Don't stop, and don't wait for a human. Find the workaround, write it down in the issue, and carry on. For example:
- **Too slow:** precompute offline and ship a table or JSON, cache, vectorize, sample less, prune.
- **Library not allowed:** implement the small piece yourself in the allowed stack.
- **Rate-limited by GitHub:** wait 3 minutes, then retry.
- **Blocked on another ticket:** pick a different hypothesis.
- **Eval too slow to iterate:** build a faster proxy evaluation, check that it agrees with the full one on 2 or 3 known results, then use it for screening.

Only stop to ask a human when a step is irreversible, such as a submission. Submissions are always human.

## Never
- Merge anything, edit protected files, force-push, or submit anything.
- Claim an improvement measured on data you tuned on.
- Skip writing down a result. A failed idea that isn't recorded gets retried by someone else.

## The metric (Poker)
- **Bar:** points against the field from `tools/sim.py` (3 seeds × 1000 deals, duplicate format), at **both** `--time-bank 8` (the real bank) and `--time-bank 4` (the safety margin). Currently **25.0 / 36 at 8 s and 17.5 / 36 at 4 s** (`findings/9-field.md`, or a newer field findings file if one exists). We lose to **tag** and **exploiter**.
- **Evaluate:** `.venv/bin/python tools/sim.py --hero agent.py --field tools/opponents/*.py baseline-bots/*.py --seeds 3 --time-bank 8` (and `--time-bank 4`), with `--json` to a log under `data/`. To compare variants, run two heroes on different ports, or put the variant behind a parameter so the sweep can toggle it.
- **Safety checks:** 0 errors, 0 forfeits, bank never emptied, max single decision under 100 ms, `.venv/bin/python -m pytest -q` passes. A crash in the tournament loses the whole match, so safety outranks points.
- **Submission:** when a merged change raises the bar, comment the new master SHA on issue #14 so a human resubmits it.

## Idea seeds (Poker)
- **Parameter search on the CPU:** expose the policy's thresholds (call and raise equity cutoffs, bluff frequency, raise-size choice) as parameters, then grid or random search them against the field. This is cheap in tokens and often the biggest gain.
- **Beat the thinking bots:** study tag and exploiter in `tools/opponents/`. Find their fold-to-raise and calling ranges, and exploit them through the opponent model.
- **Time allocation:** spend the time bank where it matters (big pots, turn and river), not evenly across hands.
- **Precompute offline:** preflop equity for every canonical hand, and flop texture buckets, shipped as JSON so decisions are lookups.
- **Value and bluff balance** by street, and position-aware aggression (the button acts last after the flop).
- **New sparring bots** that copy styles likely in the room, so wins generalize beyond our own field.
