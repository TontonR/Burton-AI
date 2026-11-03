---
id: cli
name: CLI design
desc: arguments, exit codes and help that work
tier: optional
priority: 82
---
# CLI design

- Use `argparse` (or the project's existing parser); do not hand-parse flags.
- Every option has a help line and the default in it.
- Errors go to stderr, normal output to stdout.
- Exit `0` on success, non-zero on failure; document the codes.
- Never prompt for input when stdin is not a TTY.
- Support `--help` and one real example in the description.
- Keep the command name and flags stable once users depend on them.
