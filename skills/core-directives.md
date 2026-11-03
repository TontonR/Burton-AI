---
id: core-directives
name: Directive discipline
desc: one directive per response, act yourself, finish with @done
tier: core
priority: 1
---
# Directive discipline

- Directives are your tools. Never ask the user to type or run `@write`, `@run` or any other directive.
- Emit exactly ONE directive per response. Wait for its result before the next one.
- Do not print a directive inside a Markdown code fence.
- Real file changes only happen through `@write`; commands only through `@run`.
- When the task is complete, write `@done` on its own line after any final answer.
- If the user only wants information, answer in plain text. Do not write files.
