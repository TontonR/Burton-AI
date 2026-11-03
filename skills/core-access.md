---
id: core-access
name: Real file access
desc: the project is readable; never refuse to open a file
tier: core
priority: 0
---
# Real file access

- You are inside the project root. The files are yours with `@ls` and `@read`.
- If the user names a file (`prompt.md`, `README.md`, `src/app.py`...), reply with `@read <path>`.
- Never say you cannot access, open or read a project file. Never ask for permission to inspect it.
- If a path fails, run `@ls <folder>` and try the real name.
- `@read` returns line numbers. Use the text, not the numbers.
- Use `@read` instead of `@run type`: it needs no confirmation and is safer.
