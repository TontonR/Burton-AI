---
id: core-edit
name: Safe editing
desc: read before overwrite, write the whole file, keep changes minimal
tier: core
priority: 2
---
# Safe editing

- Read an existing file with `@read` before overwriting it. New files need no read.
- `@write` replaces the WHOLE file. Include every line, with no cuts and no code fences.
- Start the body on the line after `@write` and close it with `@endwrite`.
- Copy the real content from `@read`; do not invent, summarise or describe it.
- Drop the line numbers that `@read` adds.
- Change only what the user asked for. Preserve surrounding code and style.
- Never write when the user only asks a question or a plan.
