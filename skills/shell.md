---
id: shell
name: Shell commands
desc: exit codes, pipes, timeouts and safe wildcards
tier: optional
priority: 51
---
# Shell commands

- Read the exit code: `0` means success, anything else means failure.
- Keep commands short and single-purpose; chain only when the steps belong together.
- Quote paths and arguments with spaces.
- Never use an unquoted wildcard with a delete command.
- Capture stderr; an empty stdout with a non-zero exit is still a failure.
- Set a timeout for commands that can hang.
- Do not run long interactive commands; use a non-interactive flag.
