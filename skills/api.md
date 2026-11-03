---
id: api
name: API design
desc: stable contracts, validation and clear errors
tier: optional
priority: 60
---
# API design

- The public contract is the function signature, the request/response shape and the errors.
- Validate input at the boundary and return a clear error for bad data.
- Use the correct status code: 200, 201, 400, 401, 403, 404, 409, 422, 500.
- Do not leak stack traces or internal paths to clients.
- Keep backwards compatibility; add fields, do not silently rename or remove them.
- Document the endpoint, its inputs and one example.
- Make idempotent operations idempotent.
