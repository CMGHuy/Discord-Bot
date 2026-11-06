# Lifecycle notification delivery

Admin close/cancel actions commit their recorded state and notification together. Discord delivery is at least once: a process or database failure after acceptance may repeat a notice. The same Event ID in the footer identifies the repeat; delivery does not recalculate fills or alter trading rules.

## Inspect health

System → Providers → Lifecycle notifications shows pending count, blocked count and oldest pending age. Pending includes leased and blocked work. A null health response or failed refresh means unavailable, never zero backlog. The panel warns when any event is blocked or oldest pending age exceeds 15 minutes. A blocked record is retained and retried; fixing permissions or restoring the same channel permits later delivery.

The watcher claims one event immediately before sending. Each send has a 30-second bound, each lease lasts 120 seconds, and one tick attempts at most 20 events. Retry delays are 5, 15, 60, 300, then 900 seconds indefinitely. Blocked events retry at 900 seconds; a longer numeric Discord retry_after takes precedence. Acknowledgements are retained seven days. Only records with delivery time and message ID are eligible for pruning.

Logs separate attempted, acknowledged, retried and blocked counts. An acknowledgement storage failure means Discord may have accepted the notice; intent remains leased until expiry. A zero acknowledged count is not evidence of no Discord message. Blocked state changes emit an ERROR with event ID, kind, age and safe cause; credentials and payloads are not logged.

## Rollout prerequisites

Obtain explicit deployment authorization and follow DEPLOY_HETZNER.md. Use scripts/ops/ssh-hetzner.sh for every production connection. Take and verify the normal database backup before migration, and record pending row count and event identities. deploy/deploy.sh does the stop for you: it stops bot and admin, runs `alembic upgrade head` with the new image via `docker compose run --rm --no-deps`, and only then starts the services. No old DELETE-drain consumer may run during or after the upgrade.

Confirm one Alembic head and inspect the v197 revision against that head. Upgrade to the reviewed application/schema pair while consumers remain stopped. For existing queue rows, pass the reviewed historical destination explicitly with Alembic's -x lifecycle_channel_id argument; do not silently copy a future configuration value. The invocation shape is: python -m alembic -x lifecycle_channel_id=123456789012345678 upgrade head (the number is an example, not a deploy target). An empty queue needs no destination argument. Without a valid destination, legacy rows stay pending and blocked for explicit retargeting.

Inspect the upgraded queue before resuming consumers: no original pending row disappeared; canonical event IDs and immutable payloads were retained; incomplete snapshots are visibly blocked instead of filled from current trades. Resume only the new consumer, then observe the health panel and acknowledged receipts. Validate one separately approved administrative action if a live action is needed; do not close or cancel real tracked positions merely to smoke-test delivery.

## Explicit audited retarget

Delivery always uses the event's recorded target_channel_id. Editing the global channel setting does not reroute queued work. For an undelivered event requiring a different channel, use the repository retarget operation in the authorized application environment, with the exact event ID, reviewed channel ID, named operator and incident reason. The API is:

repo.retarget(event_id, channel_id, actor=operator, reason=incident_reason, now=datetime.now(timezone.utc))

Import notify_queue_repo from swingbot.core.db.repositories.notify_queue and datetime/timezone from datetime; repo is notify_queue_repo(). Provide those values as local Python variables without exposing secrets. True means the audited row transaction committed. False means the row does not exist, is already delivered or has an active lease; inspect the record and wait for a live lease to expire instead of forcing ownership. Empty actor/reason or invalid channel raises ValueError. The history records timestamp, actor, reason and old/new channel; rendering payload and event ID do not change. Snapshot errors remain blocked after retarget, requiring a separately reviewed data repair. Never clear delivered_at or delete pending rows to force another attempt.

## Rollback

Prefer a forward repair. If rollback is required, stop the new consumer and pause admin close/cancel writes first; take and verify a database backup and record the pending queue. Application and schema rollback must be planned together. The downgrade copies promoted delivery fields into doc and preserves every queue row and immutable snapshot; a later re-upgrade preserves canonical identity.

**Image-only rollback is forbidden.** `deploy.sh` with an older image aborts at the pre-start migration ("Can't locate revision") with bot, admin and refresher stopped (restore with `unset SWING_BOT_IMAGE; docker compose up -d --no-build --wait bot admin refresher`); were it forced past that, the old image would start the old DELETE-drain consumer against the preserved v197 queue: it would re-post every acknowledged notice kept for seven days and fail on the nested payload, and old admin closes would fail their queue insert against the NOT NULL v197 columns and silently drop the notice. The only supported rollback is the point-in-time restore through `scripts/ops/rollback_to.sh` / DB_RESTORE.md, which returns schema and queue together with the image.

An old application still contains destructive draining and cannot safely consume this preserved queue. Do not start it against new pending records without an explicitly reviewed compatibility conversion and inspection. Keep delivery stopped while deciding the recovery path; queue preservation takes precedence over a nominal application restart. Use DB_RESTORE.md for a separately authorized point-in-time restore, including its scanning-paused recovery state. No rollback action is authorized merely by this document.
