---
id: code-review
name: Code review
desc: find real bugs, risks and missing tests
tier: optional
priority: 22
---
# Code review

- Report only real problems: bugs, data loss, security, broken callers, missing tests, slow paths.
- Give `file:line`, what breaks and a concrete fix.
- Rank by severity: critical, major, minor.
- Say plainly when the code is fine; do not invent findings to fill a report.
- Check the callers of every function whose signature or behaviour changed.
- Do not rewrite the code unless the user asks for a fix.
