---
id: sql
name: SQL
desc: parameters, transactions and indexes
tier: optional
priority: 62
---
# SQL

- Use parameterised queries; never interpolate user values.
- Wrap multi-step writes in a transaction.
- Read the schema before writing a query; do not guess column names.
- `SELECT` only the columns you need.
- Add an index for real query patterns, not speculatively.
- Use `EXPLAIN` before claiming a query is fast.
- Test migrations on a copy; never run destructive DDL on production data.
