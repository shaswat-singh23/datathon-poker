---
name: fanout
description: Claim several independent S or M tickets and work them in parallel, one background subagent per ticket in its own worktree, each ending in a PR. Use when someone wants to run several tickets at once from one session.
argument-hint: "[how many, default 3, max 5] [optional issue numbers]"
disable-model-invocation: true
---

Arguments: $ARGUMENTS

Follow "Picking a task", "Working a task", and "Token hygiene" in AGENTS.md. Several tickets run at once here, so selection is stricter than /work.

1. **Select.** Use the issue numbers given. Otherwise pick from unassigned open issues by priority (`must`, then `should`) whose Depends on issues are all closed. Only S or M tickets with checkable Done-when items. Their Scopes must not overlap each other or any assigned open issue. Default 3, at most 5. Fewer is fine if fewer qualify.
2. **Confirm.** Show the list (number, title, Scope, size) and wait for the user's OK. This is the only human checkpoint before the PRs.
3. **Claim.** Skip any ticket with a worktree named `N-...` already in this clone (`git worktree list`); your other sessions share your login. Then `gh issue edit N --add-assignee @me` for each, then re-check assignees. Drop any ticket someone else also holds.
4. **Launch.** Start one background subagent per ticket with worktree isolation, worktree named `N-<slug>`. Give each one this brief, with the issue number and full issue body:
   > Work issue #N in this repo. First run `git fetch origin && git rebase origin/master` in your worktree so you start from the latest master. Then follow "Working a task" steps 2 to 7 and "Token hygiene" in AGENTS.md: stay inside Scope, commit as `#N: <what>`, run every Done-when check, put any claimed result in `findings/`, rebase on origin/master, push, open the PR with `Closes #N`, and comment the PR link on the issue. Never merge. If you're blocked for more than 15 minutes or need a file outside Scope, comment on the issue saying why, unassign yourself, and stop.
5. **Wait.** Don't do ticket work in this session while they run. Note each PR link or failure as subagents finish.
6. **Report** a table: issue, PR link or blocker, and whether the PR needs the decider's merge (it claims a result). Then exit or `/clear`.

Background subagents can't stop to ask for permission. Run /work at least once in this repo first so its common commands are already allowed.
