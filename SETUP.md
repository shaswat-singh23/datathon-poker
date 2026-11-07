# Setup

## Tonight (everyone, about 10 minutes)
1. Install git, VS Code, and the GitHub CLI (`gh`). On Windows, work inside WSL2 if you have it.
   - WSL / Ubuntu: `sudo apt install gh`
   - macOS: `brew install gh`
   - Windows: `winget install --id GitHub.cli`
2. Log in so your agent can read and claim tickets: `gh auth login` (pick GitHub.com, HTTPS, log in with a browser).
3. Accept the GitHub invite, then clone:
   ```bash
   gh repo clone shaswat-singh23/<this-repo> && cd <this-repo>
   git config --global user.name "Your Name"
   git config --global user.email "you@example.com"
   ```
4. Skim AGENTS.md (3 minutes). It's how every agent on the team works.
5. Make your own free Gemini API key at aistudio.google.com. Don't share it.
6. Join the Devpost team, the Discord channel, and the Drive folder.

The stack (languages, packages) gets set up after we pick a challenge. Its commands go in "Stack setup" below.

## AI tools
- **Claude Code (VS Code):** install the "Claude Code" extension by Anthropic, sign in, open this folder, and trust it. Skills: `/triage`, `/kickoff`, `/ticket`, `/work`, `/ship-check`.
- **Cursor, Copilot, Codex:** they read AGENTS.md. Tell them "work on issue #N following AGENTS.md" or "create a ticket for <idea> following AGENTS.md."
- **ChatGPT or Gemini in a browser:** paste AGENTS.md first. A browser chat can't run git or gh, so prefer an editor-based agent for tickets.

## Tickets
```bash
gh issue list --label must                 # what matters most right now
gh issue list --search "no:assignee"       # what's free to take
gh issue list --assignee @me               # what you've claimed
gh pr list                                 # what's waiting for review
```
Add a ticket: the "Task" form on GitHub (Issues, then New issue), `/ticket <idea>`, or ask your agent.

## Parallel sessions (Claude Code)
Each ticket gets its own worktree, so sessions never touch each other's files:
```bash
claude --worktree 12-load-data      # CLI, one terminal per ticket
```
In VS Code, open a new Claude tab per ticket and run `/work`. It creates the worktree. Your `.env` is copied into each worktree automatically, so put `DATA_DIR=/absolute/path/to/your/clone/data` in it and every worktree reads the same data.

## API keys and .env
- Keys and `DATA_DIR` go in `.env` at the repo root, which git ignores. Copy `.env.example` (added at kickoff) to start.
- Never commit a key, paste one into code, or share one in chat. If one leaks, revoke it right away.
- Rate limits are per project, so four people with their own keys get four times the capacity of one shared key.

## Git cheat sheet (agents do this for you)
```bash
git fetch origin && git switch -c <name>/<N>-<slug> origin/master   # start a ticket
git add -A && git commit -m "#N: what"                               # save
git fetch origin && git rebase origin/master                         # catch up before a PR
git push -u origin HEAD                                              # share, then open a PR
```
Conflict? Ask your agent to resolve it, or ask the decider. Never force-push.

## Stack setup
Filled in at kickoff.
