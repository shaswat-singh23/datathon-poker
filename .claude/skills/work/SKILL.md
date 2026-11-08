---
name: work
description: Pick up a backlog issue and carry it through to a pull request. Use when someone says work on, take, or pick up an issue, or asks for the next task.
argument-hint: "[issue number, or blank for the next one]"
---

Issue: $ARGUMENTS

Follow "Picking a task" and "Working a task" in AGENTS.md exactly.

1. **Choose.** If no number was given, list unassigned open issues by priority:
   `gh issue list --state open --search "no:assignee" --label must`, then `should`, then `nice`.
   Pick the oldest one whose Depends on issues are all closed (`gh issue view <dep> --json state`). Say which you picked and why.
2. **Claim.** Your other sessions share your GitHub login, so assignees can't tell them apart. First run `git worktree list`: if a worktree whose name starts with `N-` exists in this clone, another of your sessions has it, so pick another. Then `gh issue edit N --add-assignee @me`, then `gh issue view N --json assignees`. If anyone else is assigned, unassign yourself and go back to step 1.
3. **Isolate.** If this session isn't already in a worktree, enter one named `N-<short-slug>`. Then run `git fetch origin && git rebase origin/master`, so the ticket starts from the latest master, including anything merged since this clone last fetched.
4. **Plan.** Read the issue, then state in a few lines how you'll meet each Done-when item inside Scope.
5. **Build.** Stay inside Scope. Work you find outside Scope gets a new issue (as in /ticket), not a fix. Commit as `#N: <what>`.
6. **Verify.** Run every Done-when check. Any result that will be claimed gets a file in `findings/`.
7. **Ship.** `git fetch origin && git rebase origin/master`, verify again, push, and open the PR as AGENTS.md describes. Comment the PR link on the issue.
8. **Report.** What changed, how each Done-when item was checked, and whether it needs a reviewer before merging. Don't merge unless the user says to.
