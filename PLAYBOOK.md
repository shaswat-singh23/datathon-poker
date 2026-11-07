# Event playbook

Times assume a ~24h event. Rescale if it's shorter.

## How we work
- **Ideas and the pitch: all of us.** We pick the challenge together, brainstorm together, and everyone presents the parts they built.
- **Building: the backlog.** Every piece of work is a GitHub issue. People point their agents at tickets with `/work` (Claude Code) or "work on #N following AGENTS.md" (any other tool). New ideas go in with `/ticket` or the issue form.
- **Decider** (still pulls tickets): ranks the backlog, promotes to `must`, says no, calls the freezes, and makes sure the story tickets land on time. Ties go to the decider so we don't spend time debating.
- **Story is tickets:** kickoff creates `must` story tickets with deadlines (README draft, demo script, figures, presentation, backup video). The presentation is drafted by an agent from `findings/` and merged PRs, so those need to stay accurate all along.
- **Verification is everyone's job:** a ticket that produces a claimed number doesn't merge until someone else checks it.

## Timeline
| When | What |
|---|---|
| 0:00 to 0:45 | Everyone reads the challenges. Run `/triage`. Decide by 0:45, no later. |
| 0:45 to 1:15 | Decider runs `/kickoff`: stack, skeleton, SETUP.md, first wave of tickets. Everyone else gets data into Drive and reads the rubric. |
| 1:15 | Everyone pulls, runs "Stack setup" in SETUP.md, and claims a first-wave ticket. |
| 1:15 to 3:00 | Build. First results with baselines. |
| 3:00 | Sync. Commit to an angle or switch using the triage kill criteria. Last free switch. |
| 3:00 to T-6h | Build. Sync every 3 hours. |
| Overnight | Sleep in shifts, 2 people at a time, 3 to 4 hours each. Agents can keep running tickets. |
| T-6h | Feature freeze. Only `bug` and story tickets from here. |
| T-4h | Code freeze. Run `/ship-check`. |
| T-4h to T-3h | Agent drafts the presentation. Split sections by who built what. Rehearse once with the live demo. |
| T-3h | Record the backup demo video. |
| T-1h | Submit. Devpost gets slow near the deadline. |

## Sync (10 minutes, every 3 hours)
1. Each person: what merged, what's in progress, what's blocked.
2. Review open PRs that need a second pair of eyes.
3. Decider re-ranks the backlog: promote, demote, close what we won't get to.
4. State the current headline result. If nobody can, that's the next `must` ticket.

## Rules of thumb
- One question answered convincingly beats five answered shallowly.
- Everything in the final demo answers a question a sponsor would ask.
- When an agent's numbers look great, someone else checks them before anyone celebrates.
- A backlog that only grows means the decider isn't saying no enough.
