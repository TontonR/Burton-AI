---
id: clean-code
name: Clean code
desc: small functions, clear names, no premature abstraction
tier: optional
default: true
priority: 11
---
# Clean code

- Names say what the thing is or does. Avoid `data`, `tmp`, `x`, `manager` when a real word exists.
- Keep functions small and at one level of abstraction.
- Do not add an abstraction, base class, config option or dependency until it is needed.
- Delete dead code instead of commenting it out.
- Prefer plain control flow over clever one-liners.
- Keep the project's existing structure and conventions; consistency beats taste.
- Comments explain why, not what. No commented-out code.
