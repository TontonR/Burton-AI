---
id: regex
name: Regular expressions
desc: readable patterns, tested edge cases, no catastrophic backtracking
tier: optional
priority: 63
---
# Regular expressions

- Escape literal dots, brackets and backslashes.
- Anchor the pattern when the whole string must match (`^...$`).
- Test with real examples: match, no match, empty string, unicode.
- Use named groups when there is more than one capture.
- Prefer `re.fullmatch` or explicit parsing when the pattern becomes unreadable.
- Avoid nested quantifiers like `(a+)+` on untrusted text.
- Compile patterns once if they are reused in a loop.
