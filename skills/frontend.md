---
id: frontend
name: Frontend
desc: semantic HTML, simple CSS, accessible by default
tier: optional
priority: 70
---
# Frontend

- Use semantic elements: `header`, `nav`, `main`, `button`, `label`.
- A clickable action is a `button`, not a `div` with a click handler.
- Every input has a `label`; every image has useful `alt` text.
- Keep CSS small and local; do not add a framework for one component.
- Use responsive units and test at a narrow width.
- Do not block the page on a failing network request; show an error state.
- Keep JavaScript out of HTML attributes when a module is simpler.
