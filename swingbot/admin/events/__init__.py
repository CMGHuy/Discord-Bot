"""Real-time event push: Postgres NOTIFYs, the browser hears.

Spec: `docs/superpowers/specs/implemented/2026-08-08-v12-realtime-push-design.md`.

Three pieces, in dependency order:

- `db_listener.py` — one LISTEN connection, turning NOTIFYs into named event
  types (the file `stat()` watcher it replaced is gone, v116)
- `broker.py`  — one listener per process, fanned out to per-connection
  queues, with the concurrency cap (NG21)
- `stream.py`  — `GET /api/v1/events`, the SSE endpoint itself (NG22)

The bot and the admin are separate containers sharing Postgres; every table
write raises its NOTIFY through a trigger, and the four sources that stay
files call `notify.publish` themselves (`core/db/events.py` FILE_PUBLISHERS).
"""
