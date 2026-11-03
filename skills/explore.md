---
id: explore
name: Explore first
desc: map the project before changing it
tier: optional
default: true
priority: 10
---
# Explore first

- Before giving an opinion about a project, look: `@ls .`, then `README.md`, `AGENTS.md` and `prompt.md` if they exist.
- Never guess a file's content. If you need it, read it.
- For a broad task, write a numbered plan and execute it step by step.
- Identify the entry point, the test command and the files the change will touch before editing.
- In plan mode use only `@ls` and `@read`; deliver the plan and finish with `@done`.
