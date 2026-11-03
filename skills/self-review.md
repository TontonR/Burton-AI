---
id: self-review
name: Self review before done
desc: question your own result and verify it before finishing
tier: optional
default: true
priority: 15
---
# Self review before done

- Before `@done`, stop and review your own work as if a strict reviewer checked it.
- Re-read the original request line by line. List every requirement it contains and confirm each one is actually implemented, not just mentioned.
- Trace the real execution path with concrete input: what the first screen shows, what each option does, what happens on bad input, and how the program exits. Find the bug yourself instead of waiting for the user.
- Check the edges the request implies: empty values, wrong types, first and last item, repeated use, and the end condition.
- Run the smallest real check you can (`@run python -m py_compile file.py`, a test, a smoke command). A pass means the command printed `exit 0`; silence or your own belief is not evidence.
- If the check fails, fix the cause and verify again. Do not finish with a known error.
- Ask yourself once: "What is missing or wrong that I have not tested yet?" If the answer is real, fix it. Only then write `@done`.
