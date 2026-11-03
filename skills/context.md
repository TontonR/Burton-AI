---
id: context
name: Context management
desc: keep the working context small and relevant
tier: optional
priority: 31
---
# Context management

- Read only the files the task needs. Use `@read path start-end` for large files.
- Never dump a whole repository into the answer.
- Keep the goal, the constraints and the verified facts in mind; drop the rest.
- Use `@agent` for read-only research that would fill the context with files.
- When the conversation is long, summarise the state in a few lines before continuing.
- Quote only the lines you need from an error or a file.
