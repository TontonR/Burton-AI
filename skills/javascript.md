---
id: javascript
name: JavaScript and TypeScript
desc: modules, async, types and real errors
tier: optional
priority: 71
---
# JavaScript and TypeScript

- Prefer `const`; use `let` only when reassigning. Never `var`.
- Use ES modules and explicit imports.
- `async` functions must handle rejection; do not leave floating promises.
- Check `response.ok` before parsing a fetch response.
- In TypeScript, avoid `any`; model the real shape or use `unknown` and narrow it.
- Read `package.json` before adding a script or dependency.
- Keep browser and Node code separate.
