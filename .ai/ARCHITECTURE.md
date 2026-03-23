# MIND Architecture Decision Record

> Last updated: 2026-03-23 — Project reset to v0.0.0 (fresh start)

---

## Status

Architecture is **not yet defined**. This file will be populated as the
project's structure is established.

## Guiding Principles (carried over)

1. **Layer separation**: Upper layers call down only. Never import from a higher layer.
2. **Store abstraction**: All persistence goes through an abstraction protocol/interface.
3. **Dependency injection**: Single composition root; no service instantiation outside it.
4. **Contract-first**: Use typed request/response models for all public interfaces.
5. **Deterministic testing**: Tests must work without external services or network.
