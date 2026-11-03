---
id: refactor
name: Safe refactor
desc: small behaviour-preserving steps with tests
tier: optional
priority: 21
---
# Safe refactor

- Refactoring changes structure, not behaviour.
- Make sure the tests pass before you start.
- Move in small steps; run the tests after each one.
- Do not mix a refactor with a feature or a bug fix in the same change.
- Keep the public interface unless the user asks to change it.
- If there are no tests, add a small one before the risky part.
