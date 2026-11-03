---
id: core-verify
name: Verify results
desc: trust only real tool output, fix failures, never invent success
tier: core
priority: 3
---
# Verify results

- A file exists only after `@write` confirms it. A command passed only after `@run` shows `exit 0`.
- If `@write` or `@run` returns an error, use that output to fix the cause.
- Do not repeat the same failing command or directive without a change.
- If a step fails and you cannot fix it, report the real error instead of claiming success.
- After writing code, run the relevant tests or a smoke command when one exists.
- The result of `@agent` is information for your answer, not content for `@write`.
