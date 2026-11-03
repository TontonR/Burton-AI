---
id: security
name: Security
desc: validate input, protect secrets, avoid injection
tier: optional
priority: 25
---
# Security

- Treat every external value as untrusted: request data, file contents, environment, command output.
- Never build shell commands or SQL by concatenating user input.
- Validate paths stay inside the project; reject `..` and absolute paths.
- Never log, print or commit secrets. Read them from environment variables.
- Use parameterised queries and safe deserialisation (`json`, not `pickle` on untrusted data).
- Fail closed on permission checks.
- Do not add a dependency without checking that it is maintained.
