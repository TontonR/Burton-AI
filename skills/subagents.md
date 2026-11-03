---
id: subagents
name: Subagents
desc: delegate read-only research and keep the parent context clean
tier: optional
priority: 32
---
# Subagents

- Use `@agent` when research would require reading many files.
- Give one clear question and the paths or clues to start from.
- The subagent is read-only: it can `@ls` and `@read`, not write or run.
- Treat its answer as a report. Verify anything you will write or claim.
- Do not delegate a task you can finish with one `@read`.
- Keep the final answer in the parent; do not paste the whole subagent transcript.
