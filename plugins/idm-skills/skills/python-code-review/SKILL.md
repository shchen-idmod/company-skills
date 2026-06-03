---
name: python-code-review
description: Use when reviewing Python code for correctness, style, security, and maintainability. Triggers on requests to review, audit, or critique Python files, pull requests, or snippets. Applies the organization's Python standards.
---

# Python Code Review

When reviewing Python code, evaluate it against the following dimensions and
report findings grouped by severity (blocker / warning / nit).

## Checklist

1. **Correctness** — logic errors, off-by-one, unhandled edge cases, incorrect
   exception handling.
2. **Security** — injection risks, unsafe deserialization, secrets in code,
   unvalidated input.
3. **Style** — adherence to PEP 8 and the org style guide; naming, typing,
   docstrings.
4. **Maintainability** — function length, duplication, unclear abstractions,
   missing tests.

## Output format

Produce a short summary, then a table of findings with file:line, severity, and
a suggested fix. Keep suggestions concrete.
