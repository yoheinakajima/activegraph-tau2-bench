"""Dry-run reactive manager planning helpers.

The package is intentionally plan-only: it reads fixture-backed trace, graph,
and state-packet artifacts and emits deterministic replay/fork/diff plans
without executing tau2 control flow or calling LLM/API services.
"""
