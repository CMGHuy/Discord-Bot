# Durable lifecycle notifications — health and final verification

**Bump:** bot patch, ui patch
**Edge:** harvest
**Screen:** harvest-headroom docs/superpowers/results/2026-10-28-notification-delivery-evidence.md
**Spec:** [Approved v197 spec](../specs/2026-10-28-v197-durable-lifecycle-notifications.md)

Use the [implementation index](2026-10-28-v197-durable-lifecycle-notifications_0-index.md) for the goal, global constraints, frozen contracts, execution order and parallelisation. This part follows V197-6b. The final task runs the full verification once, records real evidence and hands off to the normal close-out ritual. Nothing in this document authorizes a production deployment.

# Phase 4: Expose backlog truth and prove recovery

### Task V197-7: Expose truthful backlog health and a responsive operator warning
**Model:** sonnet — additive health projection and a small accessible status panel.

**Files:** Modify `swingbot/admin/api_v1/ops_health.py`, `tests/admin/test_api_v1_ops_health.py`, `frontend/src/app/api/models.ts`, `frontend/src/app/stores/system.store.ts`, `frontend/src/app/stores/system.store.spec.ts`, and `frontend/src/app/workspaces/system/scan-tab.ts`. Create `frontend/src/app/workspaces/system/notification-health-panel.ts` and `frontend/src/app/workspaces/system/notification-health-panel.spec.ts`. Add the required `notifications: null` fixture property in `frontend/src/app/workspaces/system/provider-health-panel.spec.ts` and `frontend/src/app/workspaces/system/swallowed-errors-panel.spec.ts`; these two existing typed `SystemHealth` literals must compile with the additive required field.

**Interfaces:** Consume repository `health(*, now, conn=None) -> dict` from V197-2b. Produce required `SystemHealth.notifications: NotificationHealth | null`, with `NotificationHealth = {pending_count: number; oldest_pending_age_seconds: number | null; blocked_count: number}`. The new `NotificationHealthPanel` uses inputs `health: NotificationHealth | null` and `stale: boolean`. It treats an absent runtime projection as unknown as well, so a rolling frontend/backend mismatch cannot paint healthy zeroes. Use explicit stale state from `healthError` and clear obsolete store health on fetch failure.

- [ ] **Step 1: Pin the backend projection and unknown behavior.** Add these tests to `tests/admin/test_api_v1_ops_health.py`, using its existing `logged_in`, `telemetry_rows`, `_health`, `assert_shape`, and `NULLABLE_NUMBER`. Add `"notifications": (dict, type(None))` to the exact top-level shape in `test_nothing_recorded_yet_is_empty_not_an_error`; keep all existing shape keys. These tests must run against the existing database fixtures after the required replicate-prod-db preflight.

```python
def test_notification_health_empty_is_known_zero(logged_in, telemetry_rows):
    health = _health(logged_in)["notifications"]
    assert_shape(health, {"pending_count": int, "oldest_pending_age_seconds": NULLABLE_NUMBER,
                         "blocked_count": int}, where="notifications")
    assert health == {"pending_count": 0, "oldest_pending_age_seconds": None,
                      "blocked_count": 0}


def test_notification_health_passes_only_public_projection(logged_in, telemetry_rows, monkeypatch):
    from types import SimpleNamespace
    from swingbot.admin.api_v1 import ops_health

    seen = []
    projection = {"pending_count": 3, "oldest_pending_age_seconds": 901.5, "blocked_count": 1}

    def health(*, now):
        seen.append(now)
        return projection

    monkeypatch.setattr(ops_health, "notify_queue_repo", lambda: SimpleNamespace(health=health))
    body = _health(logged_in)
    assert body["notifications"] == projection
    assert set(body["notifications"]) == set(projection)
    assert len(seen) == 1 and seen[0].utcoffset().total_seconds() == 0


def test_notification_query_outage_is_unknown_without_private_details(
        logged_in, telemetry_rows, monkeypatch, caplog):
    from types import SimpleNamespace
    from swingbot.admin.api_v1 import ops_health

    def fail(*, now):
        raise RuntimeError("private connection credentials")

    monkeypatch.setattr(ops_health, "notify_queue_repo", lambda: SimpleNamespace(health=fail))
    body = _health(logged_in)
    assert body["notifications"] is None
    assert body["providers"] == []
    assert body["swallowed"] == []
    assert "private connection credentials" not in json.dumps(body) + caplog.text
    assert "notification_health_unavailable" in caplog.text
```

Add this test inside the existing `SystemStore` describe block in `frontend/src/app/stores/system.store.spec.ts`; it uses the current `store`, `backend`, and `HEALTH` fixtures. Set `notifications: null` in that file's existing HEALTH literal too. The test proves failure after a successful fetch, not merely an initial null state.

```typescript
it('clears old notification health after a failed refresh and recovers on success', () => {
  const first = {
    ...HEALTH,
    notifications: { pending_count: 0, oldest_pending_age_seconds: null, blocked_count: 0 },
  };
  store.resolveHealth().subscribe();
  backend.expectOne('/api/v1/system/health').flush(first);
  expect(store.health()?.notifications?.pending_count).toBe(0);

  store.resolveHealth().subscribe();
  backend.expectOne('/api/v1/system/health').flush(
    { error: { code: 'unavailable', message: 'down' } },
    { status: 503, statusText: 'Service Unavailable' },
  );
  expect(store.health()).toBeNull();
  expect(store.healthError()).toBe('The admin is not responding.');

  const recovered = {
    ...HEALTH,
    notifications: { pending_count: 2, oldest_pending_age_seconds: 901, blocked_count: 1 },
  };
  store.resolveHealth().subscribe();
  backend.expectOne('/api/v1/system/health').flush(recovered);
  expect(store.health()?.notifications).toEqual(recovered.notifications);
  expect(store.healthError()).toBeNull();
});
```

Create the complete panel spec below. Its component fixture follows the existing provider-health panel's zoneless TestBed pattern. The 900-second boundary is strict; null age with zero pending is a known empty queue, while a null overall projection is unavailable.

```typescript
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { NotificationHealth } from '../../api/models';
import { NotificationHealthPanel } from './notification-health-panel';

const EMPTY: NotificationHealth = {
  pending_count: 0, oldest_pending_age_seconds: null, blocked_count: 0,
};

function render(health: NotificationHealth | null, stale = false): HTMLElement {
  const fixture = TestBed.createComponent(NotificationHealthPanel);
  fixture.componentRef.setInput('health', health);
  fixture.componentRef.setInput('stale', stale);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('NotificationHealthPanel', () => {
  beforeEach(() => TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection()],
  }));

  it('shows a known empty queue without an alert', () => {
    const el = render(EMPTY);
    expect(el.textContent).toContain('No pending notifications');
    expect(el.querySelector('[role="alert"]')).toBeNull();
    expect(el.querySelector('[role="status"]')).not.toBeNull();
  });

  it.each([null, undefined])('shows unknown for an absent health projection: %s', (health) => {
    const el = render(health ?? null);
    expect(el.textContent).toContain('Notification delivery status unavailable');
    expect(el.textContent).not.toContain('No pending notifications');
    expect(el.querySelector('dl')).toBeNull();
  });

  it('does not display stale zeroes as healthy', () => {
    const el = render(EMPTY, true);
    expect(el.textContent).toContain('Notification delivery status unavailable');
    expect(el.textContent).not.toContain('No pending notifications');
    expect(el.querySelector('dl')).toBeNull();
  });

  it.each([
    [0, 900, false], [0, 901, true], [1, 0, true], [0, null, false],
  ] as const)('warns only for blocked work or age over fifteen minutes', (blocked, age, warning) => {
    const el = render({ pending_count: 2, blocked_count: blocked, oldest_pending_age_seconds: age });
    expect(el.querySelector('[role="alert"]') !== null).toBe(warning);
    expect(el.textContent?.includes('Delivery needs attention')).toBe(warning);
  });

  it('shows pending and blocked counts and the recorded oldest age', () => {
    const el = render({ pending_count: 3, blocked_count: 1, oldest_pending_age_seconds: 960 });
    const values = Array.from(el.querySelectorAll('dd')).map((entry) => entry.textContent?.trim());
    expect(values).toEqual(['3', '1', '16 min']);
    expect(el.textContent).toContain('same event ID');
    expect(el.textContent).toContain('retry');
  });

  it('keeps missing age unknown when work is pending', () => {
    const el = render({ ...EMPTY, pending_count: 1 });
    expect(el.textContent).toContain('Unknown');
    expect(el.textContent).not.toContain('No pending notifications');
  });
});
```

- [ ] **Step 2: Run targeted red checks.** Run `python scripts/dev/testrun.py file tests/admin/test_api_v1_ops_health.py`. In `frontend`, run `npm test -- --include src/app/workspaces/system/notification-health-panel.spec.ts` and `npm test -- --include src/app/stores/system.store.spec.ts`. Missing `notifications` and missing component/import errors are expected before implementation. No full suite in this task.

- [ ] **Step 3: Add the API projection and required frontend shape.** In `swingbot/admin/api_v1/ops_health.py`, add imports `logging`, `datetime`/`timezone` from `datetime`, and `notify_queue_repo` from `swingbot.core.db.repositories.notify_queue`. Add the complete helper below, and add the dictionary entry `"notifications": _notification_health(),` to `get_system_health`'s existing response. Update the module description to mention the third panel. Keep provider and swallowed-error behavior intact; the queue failure has its own safe log and null value.

```python
log = logging.getLogger(__name__)


def _notification_health() -> dict | None:
    try:
        return notify_queue_repo().health(now=datetime.now(timezone.utc))
    except Exception:
        log.error("notification_health_unavailable")
        return None
```

In `frontend/src/app/api/models.ts`, insert this exported interface immediately before the existing `SystemHealth`, then add `notifications: NotificationHealth | null;` to `SystemHealth`. Preserve all v194 additions and all unrelated interfaces; do not replace the large models file. Add `notifications: null` to the three existing HEALTH fixtures listed in Files.

```typescript
export interface NotificationHealth {
  pending_count: number;
  oldest_pending_age_seconds: number | null;
  blocked_count: number;
}
```

In `frontend/src/app/stores/system.store.ts`, replace only its existing `resolveHealth` declaration with the following. Replace the outdated health-state comment claiming failed refreshes keep the prior payload with: `Health panels are unknown until a successful answer; a failed refresh clears the old payload and records healthError.`

```typescript
const resolveHealth = (): Observable<void> => routeRequest(api.systemHealth(), {
  start: () => undefined,
  next: (health) => patchState(store, { health, healthError: null }),
  error: (error) => patchState(store, {
    health: null,
    healthError: error.code === 'unavailable'
      ? 'The admin is not responding.' : error.message,
  }),
});
```

- [ ] **Step 4: Implement the responsive status panel and wire it into Scan.** Create `frontend/src/app/workspaces/system/notification-health-panel.ts` with this complete component. It has no new actions or paging; counts and age form a small definition list. The parent already owns `--section-gap`. Display one column on phones and three on tablet/desktop, with wrapping at every width. An unknown status uses role=status; the known breach uses role=alert and words as well as color.

```typescript
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { NotificationHealth } from '../../api/models';
import { Panel } from '../../ui/layout';

function ageText(value: number | null): string {
  if (value === null) return 'Unknown';
  if (value < 60) return `${Math.floor(value)} sec`;
  return `${Math.floor(value / 60)} min`;
}

@Component({
  selector: 'sb-notification-health-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel],
  template: `
    <sb-panel heading="Lifecycle notifications">
      <div class="content" [attr.role]="warning() ? 'alert' : 'status'" aria-atomic="true">
        @if (current(); as status) {
          @if (warning()) {
            <p class="warning">Delivery needs attention: notifications are blocked or have waited over 15 minutes.</p>
          } @else if (status.pending_count === 0) {
            <p>No pending notifications.</p>
          } @else {
            <p>Notifications are waiting for delivery.</p>
          }
          <dl>
            <div><dt>Pending</dt><dd class="num">{{ status.pending_count }}</dd></div>
            <div><dt>Blocked</dt><dd class="num">{{ status.blocked_count }}</dd></div>
            <div><dt>Oldest pending</dt><dd>{{ oldest() }}</dd></div>
          </dl>
        } @else {
          <p>Notification delivery status unavailable.</p>
        }
        <p class="explain">
          Close and cancel notices remain pending until delivery is recorded and retry automatically.
          A repeated Discord notice carries the same event ID in its footer.
        </p>
      </div>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    .content { display: grid; gap: var(--space-10); font-size: var(--text-table); line-height: 1.5; }
    p { margin: 0; overflow-wrap: anywhere; }
    .warning { color: var(--neg); font-weight: 600; }
    .explain, dt { color: var(--text-secondary); }
    dl { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--space-10); margin: 0; }
    dl > div { min-width: 0; }
    dt, dd { margin: 0; overflow-wrap: anywhere; }
    @media (max-width: 639px) {
      dl { grid-template-columns: minmax(0, 1fr); }
      dl > div { display: flex; gap: var(--space-10); align-items: baseline; flex-wrap: wrap; }
    }
  `,
})
export class NotificationHealthPanel {
  readonly health = input<NotificationHealth | null>(null);
  readonly stale = input(false);
  protected readonly current = computed(() => this.stale() ? null : this.health());
  protected readonly warning = computed(() => {
    const value = this.current();
    return !!value && (value.blocked_count > 0 || (value.oldest_pending_age_seconds ?? 0) > 900);
  });
  protected readonly oldest = computed(() => {
    const value = this.current();
    if (!value || value.pending_count === 0) return 'None';
    return ageText(value.oldest_pending_age_seconds);
  });
}
```

In `frontend/src/app/workspaces/system/scan-tab.ts`, add the import `import { NotificationHealthPanel } from './notification-health-panel';`, add `NotificationHealthPanel` to the existing component imports array, and insert the following immediately before `<sb-provider-health-panel ...>`. Keep existing health-error copy and parent grid spacing.

```html
<sb-notification-health-panel
  [health]="store.health()?.notifications ?? null"
  [stale]="store.healthError() !== null"
/>
```

- [ ] **Step 5: Verify targeted behavior and responsive layout.** Re-run the backend and two frontend commands from Step 2; also run, in `frontend`, `npm test -- --include src/app/workspaces/system/provider-health-panel.spec.ts` and `npm test -- --include src/app/workspaces/system/swallowed-errors-panel.spec.ts` after changing their required fixtures. Require green results; backend has 0 failed and 0 xfailed. Run `python scripts/dev/complexity_gate.py` and, in `frontend`, `npx eslint src/app/workspaces/system/notification-health-panel.ts src/app/workspaces/system/notification-health-panel.spec.ts src/app/stores/system.store.ts src/app/workspaces/system/scan-tab.ts`. Do not broaden to a full suite here. V197-8b builds the final SPA once and records the mandatory three-width layout audit before merge; inspect this component there in empty, pending, blocked, aged and unknown states at 390/768/1440. No table or control was added, so the existing pager and hit-area rules need no new exceptions.

- [ ] **Step 6: Commit the verified health surface.** After controller review and freshness checks, stage the ten Files paths explicitly; commit `feat(v197): surface lifecycle backlog and unknown delivery health`. The plan author does not execute this step.

### Task V197-8: Verify integrated recovery and document safe rollout and rollback
**Model:** sonnet — integrated failure recovery, operational documentation and one final verification gate.

**Files:** Create `tests/commands/test_lifecycle_delivery_integration.py` and `docs/deploy/LIFECYCLE_NOTIFICATIONS.md`. Modify `tests/suites.toml` only if the suite-capacity check requires a feature split. V197-8b owns final full verification, evidence and close-out after these integrated regressions pass.

**Interfaces:** Consume the complete V197-1 through V197-7 implementation. Integration uses real `close_plan_atomic`, `cancel_plan_atomic`, `close_legacy_atomic`, queue repository and `deliver_lifecycle_tick`, with fake Discord transport only. Fixtures are `store_db` from `tests/db/conftest.py` (exported through `tests/conftest.py`), `_plan`/`_trade` from `tests/admin/test_api_v1_trades.py`, and the existing repository classes. Existing schema upgrade/downgrade, independent-connection concurrency, stale-token fencing and authoritative rollback tests remain part of the final full suite; do not duplicate them with mocks.

- [ ] **Step 1: Write integration regressions before verification.** Create this complete test file. The fixture disables derived post-commit hooks and supplies fixed quote/bar responses before any service call, so no market-data or production operation is performed. All authoritative mutations and queue claims use real committed Postgres transactions. Capture `queued_at` from the event for the clock instead of assuming a wall-clock date. The tests' database is the shared-container test fixture database, never a production URL; run replicate-prod-db preflight before this task's first DB test.

```python
import asyncio
from copy import deepcopy
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from swingbot import config
from swingbot.admin.api_v1 import lifecycle_commands as commands
from swingbot.admin.api_v1 import trade_commands
from swingbot.commands.scanning.lifecycle_delivery import deliver_lifecycle_tick
from swingbot.core.db.repositories.account import AccountRepository
from swingbot.core.db.repositories.notify_queue import NotifyQueueRepository
from swingbot.core.db.repositories.plans import PlanRepository
from swingbot.core.db.repositories.trades import TradeRepository
from swingbot.core.tracking import performance
from swingbot.core.tracking.performance import TradeLog
from tests.admin.test_api_v1_trades import _plan, _trade

PLAN = "19700000-0000-4000-8000-000000000001"
TRADE = "v197-integration-trade"


@pytest.fixture
def book(store_db, monkeypatch):
    monkeypatch.setattr(config, "DISCORD_CHANNEL_TRADES_HISTORY_ID", "5")
    monkeypatch.setattr(trade_commands, "_override_stamp",
                        lambda ticker: {"exit_price": 102.0, "price_source": "quote"})
    monkeypatch.setattr(commands, "_manual_close_quote", lambda ticker: 102.0)
    monkeypatch.setattr(commands.rp, "cached_daily_bars", lambda ticker: None)
    monkeypatch.setattr(TradeLog, "after_manual_close_commit", lambda self, trade: None)
    AccountRepository().save(dict(base_balance=1000.0, balance=1000.0))
    return NotifyQueueRepository()


def produce(kind):
    if kind == "cancel":
        PlanRepository().insert(_plan(PLAN, status="PENDING"))
        commands.cancel_plan_atomic(PLAN)
        return
    if kind == "plan_close":
        PlanRepository().insert(_plan(PLAN, status="ACTIVE"))
        TradeRepository().insert(performance._db_record(_trade(TRADE, plan_id=PLAN)))
        commands.close_plan_atomic(PLAN)
        return
    TradeRepository().insert(performance._db_record(_trade(TRADE)))
    commands.close_legacy_atomic(TRADE)


class Channel:
    def __init__(self, error=None):
        self.sent = []
        self.error = error

    async def send(self, **kwargs):
        if self.error is not None:
            raise self.error
        self.sent.append(kwargs)
        return SimpleNamespace(id=1000 + len(self.sent))


def bot(channel):
    async def fetch(channel_id):
        return channel

    return SimpleNamespace(get_channel=lambda channel_id: channel, fetch_channel=fetch)


def row(repo):
    rows = repo.list_all()
    assert len(rows) == 1
    return rows[0]


def tick(repo, channel, now):
    return asyncio.run(deliver_lifecycle_tick(bot(channel), repo=repo, now=lambda: now))


def instant(event):
    return datetime.fromisoformat(event["queued_at"])


def assert_notification_snapshot(channel, original, kind, title):
    assert len(channel.sent) == 1
    embed = channel.sent[0]["embed"]
    assert channel.sent[0]["content"] == embed.push_text
    assert embed.footer.text.endswith("Event " + original["event_id"])
    if title is not None:
        assert embed.title.startswith(title)
    if kind == "cancel":
        assert "Result" not in {field.name for field in embed.fields}
        assert "unfilled" in embed.description.lower()
        assert AccountRepository().load()["balance"] == 1000.0


def assert_delivery_receipt(book, original):
    receipt = row(book)
    assert receipt["payload"] == original["payload"]
    assert receipt["delivered_message_id"] == "1001"
    assert receipt["delivered_at"] is not None
    assert book.pending() == 0
    assert book.count() == 1


@pytest.mark.parametrize("kind,title", [("cancel", "Plan cancelled"),
                                        ("plan_close", "Plan closed"), ("legacy_close", None)])
def test_committed_action_reaches_discord_once_and_keeps_receipt(book, kind, title):
    produce(kind)
    original = deepcopy(row(book))
    now = instant(original)
    channel = Channel()
    counts = tick(book, channel, now)
    assert counts == dict(attempted=1, acknowledged=1, retried=0, blocked=0)
    assert_notification_snapshot(channel, original, kind, title)
    assert_delivery_receipt(book, original)
    assert tick(book, channel, now + timedelta(seconds=1))["attempted"] == 0
    assert len(channel.sent) == 1


def test_transient_send_failure_retries_the_same_recorded_snapshot(book):
    produce("legacy_close")
    original = deepcopy(row(book))
    now = instant(original)
    channel = Channel(OSError("private socket details"))
    first = tick(book, channel, now)
    assert first == dict(attempted=1, acknowledged=0, retried=1, blocked=0)
    pending = row(book)
    assert pending["payload"] == original["payload"]
    assert pending["event_id"] == original["event_id"]
    assert pending["last_error"] == "network_error"
    assert book.pending() == 1
    assert tick(book, channel, now + timedelta(seconds=4))["attempted"] == 0
    # A later edit of the source trade must never alter the queued snapshot.
    TradeRepository().patch(TRADE, {"exit_price": 999.0})
    channel.error = None
    assert tick(book, channel, now + timedelta(seconds=5))["acknowledged"] == 1
    fields = {field.name: field.value for field in channel.sent[0]["embed"].fields}
    assert "102.00" in fields["Exit"] and "999" not in fields["Exit"]
    assert row(book)["payload"] == original["payload"]
    assert row(book)["attempt_count"] == 2


def test_crash_after_claim_recovers_on_lease_expiry(book):
    produce("cancel")
    original = row(book)
    now = instant(original)
    abandoned = book.claim_one("dead-process", now=now)
    channel = Channel()
    assert tick(book, channel, now + timedelta(seconds=119))["attempted"] == 0
    assert book.pending() == 1
    assert tick(book, channel, now + timedelta(seconds=121))["acknowledged"] == 1
    assert row(book)["attempt_count"] == 2
    assert channel.sent[0]["embed"].footer.text.endswith("Event " + abandoned["event_id"])
    assert not book.acknowledge(abandoned["event_id"], abandoned["lease_token"], "stale",
                                now=now + timedelta(seconds=122))
    assert row(book)["delivered_message_id"] == "1001"


def test_database_failure_after_discord_acceptance_repeats_identifiable_event(book, monkeypatch):
    produce("plan_close")
    original = deepcopy(row(book))
    now = instant(original)
    channel = Channel()
    write = book._write

    def fail_ack(connection, event):
        write(connection, event)
        if event.get("delivered_at"):
            connection.execute(sa.text("SELECT 1 / 0"))

    with monkeypatch.context() as scoped:
        scoped.setattr(book, "_write", fail_ack)
        first = tick(book, channel, now)
    assert first == dict(attempted=1, acknowledged=0, retried=0, blocked=0)
    assert len(channel.sent) == 1
    pending = row(book)
    assert pending["delivered_at"] is None
    assert pending["delivered_message_id"] is None
    assert pending["lease_token"] is not None
    assert pending["payload"] == original["payload"]
    assert tick(book, channel, now + timedelta(seconds=119))["attempted"] == 0
    second = tick(book, channel, now + timedelta(seconds=121))
    assert second["acknowledged"] == 1 and len(channel.sent) == 2
    footers = [sent["embed"].footer.text for sent in channel.sent]
    assert footers[0] == footers[1]
    assert footers[0].endswith("Event " + original["event_id"])
    assert row(book)["delivered_message_id"] == "1002"
    assert row(book)["payload"] == original["payload"]


def test_unavailable_channel_stays_blocked_until_repaired(book):
    produce("cancel")
    now = instant(row(book))
    assert tick(book, None, now)["blocked"] == 1
    assert book.health(now=now) == dict(pending_count=1, oldest_pending_age_seconds=0.0,
                                       blocked_count=1)
    assert row(book)["last_error"] == "channel_unavailable"
    channel = Channel()
    assert tick(book, channel, now + timedelta(seconds=899))["attempted"] == 0
    assert tick(book, channel, now + timedelta(seconds=900))["acknowledged"] == 1
    assert row(book)["blocked"] is False
    assert book.health(now=now + timedelta(seconds=900))["pending_count"] == 0
```

- [ ] **Step 2: Run the new integration file narrowly and inspect failures.** After database preflight, run `python scripts/dev/testrun.py file tests/commands/test_lifecycle_delivery_integration.py`. These are characterization/integration tests over earlier tasks, so a green first run is legitimate; do not manufacture a failing application edit. If a case fails, fix the relevant implementation seam in a scoped commit with its own narrow regression, then rerun the failing file. Do not use a full-suite run for debugging.

- [ ] **Step 3: Verify suite ownership and write the operational runbook.** Run `python scripts/dev/testrun.py file tests/dev/test_suites.py` after all new tests exist. The new directories already belong to suites: commands/infra → discord; scanning → scanning; db/tracking → storage; admin → admin. No manifest edit is expected. If the 1200-test cap is exceeded, split the overflowing suite by feature with disjoint paths in `tests/suites.toml`, preserving exactly-one ownership; never increase `max_tests` or hand-list CI jobs. Follow the reported offending suite, and rerun this one file after the change.

Write `docs/deploy/LIFECYCLE_NOTIFICATIONS.md` with the following complete content. The commands are operator procedures for a separately authorized rollout, not steps to execute during implementation. The local verification below never starts a Discord bot against the production channel.

```markdown
# Lifecycle notification delivery

Admin close/cancel actions commit their recorded state and notification together. Discord delivery is at least once: a process or database failure after acceptance may repeat a notice. The same Event ID in the footer identifies the repeat; delivery does not recalculate fills or alter trading rules.

## Inspect health

System → Scan → Lifecycle notifications shows pending count, blocked count and oldest pending age. Pending includes leased and blocked work. A null health response or failed refresh means unavailable, never zero backlog. The panel warns when any event is blocked or oldest pending age exceeds 15 minutes. A blocked record is retained and retried; fixing permissions or restoring the same channel permits later delivery.

The watcher claims one event immediately before sending. Each send has a 30-second bound, each lease lasts 120 seconds, and one tick attempts at most 20 events. Retry delays are 5, 15, 60, 300, then 900 seconds indefinitely. Blocked events retry at 900 seconds; a longer numeric Discord retry_after takes precedence. Acknowledgements are retained seven days. Only records with delivery time and message ID are eligible for pruning.

Logs separate attempted, acknowledged, retried and blocked counts. An acknowledgement storage failure means Discord may have accepted the notice; intent remains leased until expiry. A zero acknowledged count is not evidence of no Discord message. Blocked state changes emit an ERROR with event ID, kind, age and safe cause; credentials and payloads are not logged.

## Rollout prerequisites

Obtain explicit deployment authorization and follow DEPLOY_HETZNER.md. Use scripts/ops/ssh-hetzner.sh for every production connection. Take and verify the normal database backup before migration, and record pending row count and event identities. Stop every bot consumer and prevent admin close/cancel writes during migration; no old DELETE-drain consumer may run during or after the upgrade.

Confirm one Alembic head and inspect the v197 revision against that head. Upgrade to the reviewed application/schema pair while consumers remain stopped. For existing queue rows, pass the reviewed historical destination explicitly with Alembic's -x lifecycle_channel_id argument; do not silently copy a future configuration value. The invocation shape is: python -m alembic -x lifecycle_channel_id=123456789012345678 upgrade head (the number is an example, not a deploy target). An empty queue needs no destination argument. Without a valid destination, legacy rows stay pending and blocked for explicit retargeting.

Inspect the upgraded queue before resuming consumers: no original pending row disappeared; canonical event IDs and immutable payloads were retained; incomplete snapshots are visibly blocked instead of filled from current trades. Resume only the new consumer, then observe the health panel and acknowledged receipts. Validate one separately approved administrative action if a live action is needed; do not close or cancel real tracked positions merely to smoke-test delivery.

## Explicit audited retarget

Delivery always uses the event's recorded target_channel_id. Editing the global channel setting does not reroute queued work. For an undelivered event requiring a different channel, use the repository retarget operation in the authorized application environment, with the exact event ID, reviewed channel ID, named operator and incident reason. The API is:

repo.retarget(event_id, channel_id, actor=operator, reason=incident_reason, now=datetime.now(timezone.utc))

Import notify_queue_repo from swingbot.core.db.repositories.notify_queue and datetime/timezone from datetime; repo is notify_queue_repo(). Provide those values as local Python variables without exposing secrets. True means the audited row transaction committed. False means the row does not exist, is already delivered or has an active lease; inspect the record and wait for a live lease to expire instead of forcing ownership. Empty actor/reason or invalid channel raises ValueError. The history records timestamp, actor, reason and old/new channel; rendering payload and event ID do not change. Snapshot errors remain blocked after retarget, requiring a separately reviewed data repair. Never clear delivered_at or delete pending rows to force another attempt.

## Rollback

Prefer a forward repair. If rollback is required, stop the new consumer and pause admin close/cancel writes first; take and verify a database backup and record the pending queue. Application and schema rollback must be planned together. The downgrade copies promoted delivery fields into doc and preserves every queue row and immutable snapshot; a later re-upgrade preserves canonical identity.

An old application still contains destructive draining and cannot safely consume this preserved queue. Do not start it against new pending records without an explicitly reviewed compatibility conversion and inspection. Keep delivery stopped while deciding the recovery path; queue preservation takes precedence over a nominal application restart. Use DB_RESTORE.md for a separately authorized point-in-time restore, including its scanning-paused recovery state. No rollback action is authorized merely by this document.
```

- [ ] **Step 4: Commit integrated regressions and the runbook.** After controller review and freshness checks, stage `tests/commands/test_lifecycle_delivery_integration.py` and `docs/deploy/LIFECYCLE_NOTIFICATIONS.md`, plus `tests/suites.toml` only if changed; commit `test(v197): prove lifecycle recovery and document safe operations`. The narrow integration and suite-ownership checks must be green. Full verification belongs to V197-8b, not this task. The plan author does not execute this step.

### Task V197-8b: Run the final verification once and close out the green plan
**Model:** sonnet — evidence-based verification and the established release ritual.

**Files:** Record verification evidence in `docs/superpowers/plans/2026-10-28-v197-durable-lifecycle-notifications_0-index.md`. The close-out ritual owns `VERSION.json`, then `swingbot/admin/version_history.json`, and moving the approved spec and all plan parts. No runtime behavior is added here; temporary browser verification scripts are removed after use. Do not predict release versions or deploy production.

**Interfaces:** Consume all completed V197 tasks, the existing test-runner agent, `testrun.py full`, the Angular test/build commands, and the current authenticated Playwright layout-audit. The outcome is recorded evidence with no unresolved BLOCKING review findings, then the regular close-out. Verification failures are fixed at their source with narrow regression tests, not hidden in the release steps.

- [ ] **Step 1: Record the integrated coverage before the final gate.** Check the real test names below exist after implementation. These are existing earlier-task tests included in the final full run, not requests for another broad rerun. If one is missing, fix that omission before the final run.

| Required invariant | Actual planned test owner |
|---|---|
| Old rows survive upgrade, downgrade and re-upgrade with stable identity | `tests/db/test_v197_lifecycle_migration.py::test_downgrade_reupgrade_preserves_identity_payload_and_pending` |
| Two independent connections cannot claim the same live lease | `tests/db/test_notify_queue_delivery.py::test_concurrent_claim_skips_locked_row` |
| Expired and reclaimed workers cannot acknowledge newer ownership | `tests/db/test_notify_queue_delivery.py::test_claim_expiry_stale_ack_and_acknowledgement` and `test_expired_token_cannot_complete_without_a_new_claim` |
| Trade, plan, account, balance history and event roll back together | `tests/admin/test_lifecycle_commands_db.py::test_any_authoritative_write_failure_rolls_everything_back` |
| API refuses success when queue insertion fails | `tests/admin/test_api_v1_trade_commands.py::test_close_queue_failure_returns_503_and_rolls_back` |
| Snapshot send, transient retry, crash, duplicate ambiguity and durable blockage | New `tests/commands/test_lifecycle_delivery_integration.py` above |
| Missing health is unknown, stale health is cleared and warning is accessible | V197-7 backend/store/component tests |

- [ ] **Step 2: Perform the one final backend/frontend verification.** Ensure the current implementation checkout includes every task and no unrelated dirty files are staged. The controller dispatches `test-runner` for `python scripts/dev/testrun.py full` once; require 0 failed and 0 xfailed and record the returned summary, not a progress count. In `frontend`, run `npm test` once, then `npm run build`. Run `python scripts/dev/plan_lint.py docs/superpowers/plans/2026-10-28-v197-durable-lifecycle-notifications_0-index.md` and require PASS. A failure is repaired and rerun narrowly; a fix touching other backend files uses `testrun.py changed` as prescribed. Do not rerun the full suite after a clean merge. Do not claim that the plan author ran these commands: evidence is recorded only at implementation time.

- [ ] **Step 3: Inspect the final UI at phone, tablet and desktop widths and run the mandatory audit.** Build/start only an authenticated local replica using the project's ADMIN_USERNAME/ADMIN_PASSWORD loaded internally from `.env`, never printed or passed as arguments and never admin/admin. Use the established local startup `python admin_ui.py` on localhost:1234 after setting DATABASE_URL to the verified replica. Do not start `bot.py`. Sign in with `node frontend/scripts/browse.mjs login --base http://localhost:1234`, close that browser so its persistent profile is released, then capture `node frontend/scripts/browse.mjs shots --base http://localhost:1234 --path "system?tab=scan" --widths 390,768,1440 --out "$env:TEMP/v197-notification-health"` in PowerShell. Inspect the generated screenshots, not only a DOM assertion.

For empty, pending, blocked, aged and unavailable panel states, use local Playwright response interception on `/api/v1/system/health`, merging only its `notifications` value into the real authorized response; do not write synthetic events to the replica book or change the real health endpoint. A 503 intercepted health response proves the stale-warning path after a successful response. Check count labels, status/alert semantics, complete explanatory text, wrapping and no horizontal overflow at all three widths. The new panel adds no controls; existing touch controls still meet 44px and text remains at least 11px. Always keep a visible unknown state when projection/refresh is unavailable.

Finally run `node frontend/scripts/layout-audit.mjs --base http://localhost:1234` and require exit 0 at its default 390/768/1440 widths. This includes the merged v194 hint checks. Fix findings; do not add an allow-list entry for an off-screen/covered hint or this panel's layout. Record the audit artifact directory and verdict in the index. If local setup or authentication is unavailable, the task is incomplete; record the exact blocker instead of calling the UI verified.

- [ ] **Step 4: Commit verification evidence and complete normal close-out only when green.** Stage the index evidence explicitly; commit `docs(v197): record final lifecycle delivery verification`. Record the real backend/frontend/build/audit results and date in Handoff. Run the required staff-engineer panel over the completed implementation diff/results through the repo panel skill; resolve every BLOCKING finding. No backtest or pooled-performance claim is involved.

The controller then follows close-out and worktree-lifecycle: check concurrent worktrees before integration, merge only the verified branch, resolve bot patch and ui patch from the then-current `VERSION.json`, and use fresh UTC `*_updated` timestamps. For each line, commit its VERSION.json bump first, run `python scripts/dev/build_version_matrix.py` only after that release commit, and commit regenerated `swingbot/admin/version_history.json` separately with the same release version/summary. Run `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py` after bumping; never a second full suite after a clean merge. Move the spec and all five plan files to their appropriate implemented directories, preserving links, then remove only the authorized task worktree/branch under lifecycle safeguards. No production deployment is part of this task. The plan author executes none of these implementation, release or cleanup commands.
