---
name: ticket
description: Turn a rough idea into well-formed GitHub issues on the team backlog. Use when someone wants to add a task, feature, bug, or idea to the list.
argument-hint: "[rough idea] [optional priority: must, should, or nice]"
---

Idea: $ARGUMENTS

Follow "Ticket format" and "Adding a task" in AGENTS.md.

1. Search for duplicates: `gh issue list --state open --search "<keywords>"`. If one exists, comment the new detail there and stop.
2. Read enough of the code to write a real Scope with actual paths, and check open issues for what this depends on.
3. Bigger than L? Split it into several issues linked through Depends on.
4. For each issue: an imperative title under 60 characters, a body with the five headings, and one priority label. Use the priority the user gave, otherwise `nice`.
5. Check Scope against open issues that someone is working on (`gh issue list --state open --json number,title,assignees,body`, keep the ones with assignees). If it overlaps one, make it depend on that issue or narrow the Scope, and say which.
6. Write each body to a temp file and create the issue: `gh issue create --title "..." --body-file <file> --label <priority>`.
7. Print each issue number, title, and priority. If you split the idea into 3 or more issues, show the drafts and get an OK before creating them.
