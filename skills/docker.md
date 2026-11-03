---
id: docker
name: Docker
desc: small images, no secrets, explicit volumes
tier: optional
priority: 84
---
# Docker

- Use a small official base image and pin the tag.
- Copy the lockfile first, install dependencies, then copy the source.
- Run as a non-root user.
- Never bake secrets into an image or a layer.
- Declare volumes for data that must persist.
- Use `docker compose` for multi-service local setups.
- Test the build and one real command before reporting success.
