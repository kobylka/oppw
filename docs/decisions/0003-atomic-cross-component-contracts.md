# ADR 0003: Atomic cross-component contract changes

- Status: Accepted
- Date: 2026-07-22

## Context

Publisher, PHP, MySQL, analytics/status responses, Android models, and UI were often changed independently. This produced blank fields, HTML parsed as JSON, stale classifications, and incompatible mobile builds.

## Decision

Treat a cross-component payload as one contract. Change its producer, validation, persistence, read API, Android model/parser/UI, fixtures, and tests in one coherent change set. Prefer additive compatibility and prohibit undocumented endpoint aliases.

## Consequences

Changes require broader inspection and testing but remove guesswork at component boundaries. Partial deployments need an explicit staged compatibility design rather than accidental tolerance.
