---
id: testing
name: Testing
desc: test behaviour and edge cases after every change
tier: optional
default: true
priority: 13
---
# Testing

- Find the existing test command and use it; do not invent a new framework.
- Test behaviour, not implementation details.
- Cover the happy path, empty input, one item, many items and the error path.
- After changing code, run the smallest relevant test first, then the full suite.
- A failing test is information: fix the cause, never delete or skip the test to make it pass.
- New non-trivial logic needs one small test.
- Report the real command and the real result.
