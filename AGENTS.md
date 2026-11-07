# Team conventions

Read by Claude Code, Cursor, Codex, and Copilot. Using ChatGPT or Gemini in a browser? Paste this file in at the start.

All work is a GitHub issue. Agents do the building; humans decide what gets built and check results.

## Team
- Shaswat, Sahith, Kyle, Alex. Everyone builds by pulling tickets.
- **Decider:** Shaswat. Ranks the backlog, sets `must`, calls freezes, and is the only one who edits this file after kickoff.
- **Story:** everyone presents. Story work is `must` tickets with deadlines (created at kickoff). The decider makes sure they land on time.

## Challenge
Filled in at kickoff. The decider updates the headline at each sync.
- Challenge: ___
- Deliverables: ___
- Judging weights: ___
- Core question: ___
- Headline result: ___

## Stack
Filled in at kickoff.

## Layout
Filled in at kickoff. Defaults that hold for any challenge:
```
data/raw/     original data exactly as downloaded. NEVER modify. gitignored.
findings/     one file per result. See "Findings" below.
.env          secrets and local paths (DATA_DIR). gitignored. Copied into Claude worktrees by .worktreeinclude.
```
Code reads data from the `DATA_DIR` environment variable (default `./data`), so every worktree uses the same data without copying it.

## Ticket format
Every issue body has these five headings, in this order. The GitHub issue form produces them. Agents creating issues with `gh issue create` write them by hand.
```
### Goal
The outcome in 1 or 2 sentences, not the steps.

### Done when
- [ ] Checkable criteria: a command that runs, a number produced, a page that loads.

### Scope
Files or folders this ticket may create or change. Everything else is off limits.

### Depends on
#N, #M, or none

### Size
S (under 30 min), M (under 1 hour), or L (under 2 hours). Bigger means split it.
```
Each issue has exactly one priority label: `must`, `should`, or `nice`. Add `bug` for breakage.

## Adding a task
- Anyone can add one: the issue form on GitHub, `/ticket <idea>` in Claude Code, or `gh issue create` using the format above.
- Search open issues first. If it already exists, comment there instead.
- New tasks start as `nice`. Only the decider promotes to `should` or `must`.
- An agent that finds work outside its ticket's Scope does not do it. It creates an issue, mentions the current issue in it, and carries on.
- After feature freeze, only `bug` and story tickets get added.

## Picking a task
- Priority order: `must`, then `should`, then `nice`. Within a priority, oldest first.
- Only pick unassigned issues whose Depends on issues are all closed.
- Claim it: `gh issue edit N --add-assignee @me`. Then check the assignees again. If someone else is on it too, unassign yourself and pick another.
- One ticket per agent session. A person can run several sessions, each on its own ticket in its own worktree.

## Working a task
1. **Isolate.**
   - Claude Code: work in a worktree named `N-<slug>`. Either start with `claude --worktree N-<slug>` or ask Claude to work in a worktree with that name.
   - Other tools: `git fetch origin && git switch -c <yourname>/N-<slug> origin/master`.
2. **Stay inside Scope.** If the work needs a file outside Scope, stop, comment on the issue saying what and why, and continue only after a human OKs it.
3. **Commit small.** Messages start with the issue number: `#N: <what>`.
4. **Verify.** Check every Done-when item by actually running it. Don't assume.
5. **Sync.** `git fetch origin && git rebase origin/master`, fix any conflicts, then verify again.
6. **Open a PR.** Title `#N: <goal>`. The body has `Closes #N`, how each Done-when item was checked, and any number produced. Comment the PR link on the issue.
7. **Merge.** If the ticket produced a result that will be claimed (a number, a score, a finding), someone other than the author reviews it before merge. Anything else, the author merges once checks pass. Agents never merge without a human saying so.
8. **Blocked for more than 15 minutes?** Comment what's blocking on the issue, unassign yourself, and pick another.

## Avoiding merge conflicts
- Tickets running at the same time have non-overlapping Scope. Kickoff and the decider split work that way.
- Features live in separate files: one module per feature, and plugin-style folders (for example a `pages/` directory) instead of one file everyone edits.
- PRs stay small and merge within about 2 hours of starting. Long-lived branches cause conflicts.
- Dependency changes go in their own small PR, merged first. On a lockfile conflict, take master's lockfile and re-run the add command.
- Results go in their own files in `findings/`, never one shared file.

## Rules
1. Never edit or overwrite anything in data/raw.
2. Every result is compared against a simple baseline (naive model, random agent, rule of thumb). No baseline, no claim.
3. If a result looks too good, assume a bug or leakage until proven otherwise.
4. When combining data, check row counts before and after.
5. A number goes in `findings/` before it goes in slides or the README.
6. master always runs.
7. Secrets live in `.env` and are read from environment variables. Each person uses their own API key. Never commit or paste a key.
8. Never force-push.

## Findings
One file per result: `findings/<issue>-<slug>.md`.
```
# <title>
- Issue: #N | Author: <name> | Time: <hh:mm>
- Claim:
- Evidence: <number> from <command, script, or query>
- So what: <why a judge should care>
- Checked by: <name>, or "unchecked"
```
