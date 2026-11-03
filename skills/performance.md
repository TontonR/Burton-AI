---
id: performance
name: Performance
desc: measure before optimizing, then fix the hot path
tier: optional
priority: 24
---
# Performance

- Measure before optimizing. Without a number, it is a guess.
- Find the hot path with a profiler or timing around the suspect block.
- Fix the algorithm before micro-optimizing syntax.
- Avoid repeated file reads, network calls and nested loops over the same data.
- Cache only when the cost is measured and invalidation is clear.
- Do not trade readability for speed without evidence.
