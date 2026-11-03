---
id: errors
name: Error handling
desc: fail loudly, validate at boundaries, no silent catches
tier: optional
priority: 23
---
# Error handling

- Validate input at trust boundaries: user input, files, network, command output.
- Catch only the exceptions you can handle. Never swallow errors silently.
- Error messages say what failed and what the user can do next.
- Do not return `None` to signal several different failures.
- Preserve the original exception with `raise ... from exc` when translating it.
- Clean up resources with `with` or `finally`.
- A crash with a clear message beats corrupt data.
