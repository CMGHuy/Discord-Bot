"""Real-time event push: the admin notices `data/` change, the browser hears.

Spec: `docs/superpowers/specs/2026-08-08-v12-realtime-push-design.md`.

Three pieces, in dependency order:

- `watcher.py` — one `stat()` loop over a fixed set of paths, turning file
  modification into a named event type (NG20)
- `broker.py`  — one watcher per process, fanned out to per-connection
  queues, with the concurrency cap (NG21)
- `stream.py`  — `GET /api/v1/events`, the SSE endpoint itself (NG22)

The bot process is not involved and is not modified. It and the admin are
separate containers sharing only the bind-mounted project directory, so
the bot's writes to `data/` are the entire channel between them -- which
is why this package infers events from the filesystem rather than
receiving them.
"""
