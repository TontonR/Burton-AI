---
id: debugging
name: Debugging
desc: reproduce, isolate and find the root cause
tier: optional
default: true
priority: 20
---
# Debugging

- Reproduce the bug before changing code. If you cannot reproduce it, say what you need.
- Read the full traceback: the last line names the error, the frames show the path.
- Form one hypothesis, test it with the smallest change or command.
- Change one thing at a time; do not rewrite everything hoping it works.
- Find the root cause, not the symptom. Fix it once in the shared code.
- If a fix does not work, revert it before trying the next idea.
- Add a regression test when the bug is fixed.
