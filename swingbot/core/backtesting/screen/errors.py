"""Errors an idea module raises to the screen runner (v214 G4)."""


class IdeaError(RuntimeError):
    """An idea's own computation failed on one ticker's frame. The runner
    aborts that ticker, counts it per ticker and carries on; it never reads
    as "no event", which would shrink N silently."""
