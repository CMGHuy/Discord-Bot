# v210 — Market-shock notices and admin badge, part 2: the SPA badge, release, close-out

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v209 — Market-shock detector](../specs/2026-11-05-v209-market-shock-detector-design.md) (§ Units → *Admin*; § Track 1 tests → *Frontend*)
**Index:** [`_0-index.md`](2026-11-06-v210-market-shock-notices-and-badge_0-index.md) — Goal, Global Constraints, Review Focus, Parallelisation and the task ledger live there and bind every task below.
**Brief:** `.superpowers/briefs/2026-11-05-v209-market-shock-detector.md` §3.9–3.10 (tape), §4 (frontend spec pattern), D8 (rollback).

Tasks: V210-3b, the SPA half of V210-3 (its API half is the last task of
part 1; split there at the 1500-line cap), V210-4 (release: bot patch, ui
patch, deploy, shadow checks) and V210-5 (`/panel` and `/close-out` without a
second bump). `V209-*` ids name tasks of plan v209, merged before this plan
starts. Phone width: the shell hides the whole tape strip below 640 px, so the
badge, which lives in the tape component, shows at tablet and desktop widths
only; the shell is not edited (the index's OPEN item flags this for the
partner).

---

# Phase 2 — admin badge (continued)

### Task V210-3b: SPA market-shock badge beside the tape, at three widths

**Model:** sonnet — a badge inside an existing component plus one store signal; the layout rule (beside the tape, wrapping under it) is pinned and checked by the audit.

Second half of the ledger's V210-3 (split at the 20 KB task cap). Needs
V210-3 merged on the branch (the badge reads its API field). UI work: one
surface (the shell tape, on every route), checked at 390, 820 and 1440 px per
`docs/claude/ui-design.md` § UI tasks.

**Files:**
- Modify: `frontend/src/app/api/models.ts` (`ShockLabel`, `TapeShock`, `TapeResponse.shock?`)
- Modify: `frontend/src/app/stores/tape-feed.ts`, `frontend/src/app/stores/tape-feed.spec.ts`
- Modify: `frontend/src/app/shell/tape/tape.ts`, `tape.css`, `tape.spec.ts`

**Interfaces:**
- Consumes: V210-3's `shock` object on `GET /api/v1/market/tape`; for the visual check, `market_shock_repo().record(...)` (V209-5b, v209 (merged)), `ShockReading` / `ShockState` (V209-2..3, v209 (merged)).
- Produces: `type ShockLabel = 'NORMAL' | 'SHOCK' | 'RECOVERY'`; `interface TapeShock` with V210-3's keys; `TapeResponse.shock?: TapeShock | null`; `TapeFeed.shock: Signal<TapeShock | null>`; `export function shockSummary(s: TapeShock): string` in `tape.ts`; badge element `.shock-badge[data-label]` with copy `NORMAL` / `SHOCK` / `RECOVERY` and `VIX missing` when `vix_missing`.

**Layout rule.** The badge is a sibling *after* `.lane` inside the `sb-tape`
host, never inside `.viewport`, so the tape's clip and scroll can never cut
it. At ≥ 1024 px it sits to the tape's right on the same 32 px line; below
1024 px the host wraps and the badge takes its own 24 px line under the tape.
Below 640 px the shell hides the whole tape strip (`shell.css`), badge
included; the shell is not edited.

- [ ] **Step 1: Write the failing frontend tests**

1a. `frontend/src/app/stores/tape-feed.spec.ts` — append inside `describe('TapeFeed', ...)`, before its closing `});`:

```ts
  const shock = {
    label: 'SHOCK', since: '2026-11-05T14:45:00+00:00', as_of: '2026-11-05T15:00:00+00:00',
    breadth_pct: 42, sectors_down: 5, sectors_total: 8, spy_atr_move: -1.8, qqq_atr_move: -2.3,
    vix_level: 21.13, vix_chg_pct: 27.2, vix_missing: false,
  } as const;

  it('keeps the reply shock object (v210)', async () => {
    api.tape.mockReturnValue(of({ as_of: 'x', rows: [row('^GSPC')], shock }));
    feed.register('index', signal(['^GSPC']));
    await flush();
    expect(feed.shock()).toEqual(shock);
  });

  it('a reply without shock reads as null (detector off)', async () => {
    api.tape.mockReturnValue(of({ as_of: 'x', rows: [row('^GSPC')] }));
    feed.register('index', signal(['^GSPC']));
    await flush();
    expect(feed.shock()).toBeNull();
  });

  it('a failed refetch keeps the previous shock', async () => {
    api.tape.mockReturnValue(of({ as_of: 'x', rows: [row('^GSPC')], shock }));
    feed.register('index', signal(['^GSPC']));
    await flush();
    api.tape.mockReturnValue(throwError(() => new Error('down')));
    events.raise('scan');
    await flush();
    expect(feed.shock()).toEqual(shock);
  });
```

1b. `frontend/src/app/shell/tape/tape.spec.ts` — import `TapeFeed` from
`'../../stores/tape-feed'` and `shockSummary` from `'./tape'`; give `setup` a
fourth parameter `shock: unknown = null` and add
`{ provide: TapeFeed, useValue: { shock: () => shock } }` to its providers
(every existing test keeps passing with no badge). Append:

```ts
  const shockState = {
    label: 'SHOCK', since: '2026-11-05T14:45:00+00:00', as_of: '2026-11-05T15:00:00+00:00',
    breadth_pct: 42, sectors_down: 5, sectors_total: 8, spy_atr_move: -1.8, qqq_atr_move: -2.3,
    vix_level: 21.13, vix_chg_pct: 27.2, vix_missing: false,
  };

  it('shows no badge without a shock object (detector off)', () => {
    const el = setup([index], [stock]).nativeElement as HTMLElement;
    expect(el.querySelector('.shock-badge')).toBeNull();
  });

  it.each(['NORMAL', 'SHOCK', 'RECOVERY'])('labels the badge %s', (label) => {
    const el = setup([index], [stock], undefined, { ...shockState, label }).nativeElement as HTMLElement;
    const badge = el.querySelector('.shock-badge')!;
    expect(badge.getAttribute('data-label')).toBe(label);
    expect(badge.querySelector('.shock-label')!.textContent!.trim()).toBe(label);
    expect(badge.textContent).not.toContain('VIX missing');
  });

  it('says VIX missing when the reading has no VIX', () => {
    const missing = { ...shockState, vix_level: null, vix_chg_pct: null, vix_missing: true };
    const el = setup([index], [], undefined, missing).nativeElement as HTMLElement;
    expect(el.querySelector('.shock-badge .shock-vix')!.textContent!.trim()).toBe('VIX missing');
  });

  it('sits after the tape lane, never inside its clipped viewport', () => {
    const el = setup([index], [stock], undefined, shockState).nativeElement as HTMLElement;
    expect(el.querySelector('.lane .shock-badge')).toBeNull();
    expect(el.querySelector('.lane')!.nextElementSibling!.classList).toContain('shock-badge');
    expect(el.querySelectorAll('.cap-row').length).toBe(1);
    expect(el.textContent!.toLowerCase()).not.toContain('live');
  });

  it('carries the headline numbers in its title', () => {
    const el = setup([index], [stock], undefined, shockState).nativeElement as HTMLElement;
    expect(el.querySelector('.shock-badge')!.getAttribute('title')).toBe(
      'Market state SHOCK since 14:45 UTC · breadth 42% · sectors 5/8 · SPY -1.80 ATR · QQQ -2.30 ATR · VIX 21.13 (+27.2%)');
  });

  it('summarises a reading with no numbers as n/a', () => {
    expect(shockSummary({
      label: 'NORMAL', since: null, as_of: null, breadth_pct: null, sectors_down: null,
      sectors_total: null, spy_atr_move: null, qqq_atr_move: null, vix_level: null,
      vix_chg_pct: null, vix_missing: true,
    })).toBe('Market state NORMAL · breadth n/a · sectors n/a · SPY n/a · QQQ n/a · VIX missing');
  });
```

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/tape-feed.spec.ts` and `node frontend/scripts/ng-test.mjs frontend --include src/app/shell/tape/tape.spec.ts`
Expected: FAIL — `feed.shock is not a function`; `shockSummary` is not exported.

- [ ] **Step 2: Implement the frontend**

2a. `frontend/src/app/api/models.ts`, above `TapeResponse`:

```ts
/** v210: the market-shock detector's state, shown beside the tape. */
export type ShockLabel = 'NORMAL' | 'SHOCK' | 'RECOVERY';

export interface TapeShock {
  label: ShockLabel;
  since: string | null;
  /** The last reading's instant; null before any reading. */
  as_of: string | null;
  breadth_pct: number | null;
  sectors_down: number | null;
  sectors_total: number | null;
  spy_atr_move: number | null;
  qqq_atr_move: number | null;
  vix_level: number | null;
  vix_chg_pct: number | null;
  vix_missing: boolean;
}
```

and add to `TapeResponse`:
`/** v210: null under MARKET_SHOCK_MODE=off or before the first stepped pass. */ shock?: TapeShock | null;`

2b. `frontend/src/app/stores/tape-feed.ts`: import `TapeShock`; add
`private readonly _shock = signal<TapeShock | null>(null);` and
`readonly shock = this._shock.asReadonly();`; in `next`, after
`this._asOf.set(...)`, add `this._shock.set(response.shock ?? null);`. The
error path is untouched, so a failed refetch keeps the badge.

2c. `frontend/src/app/shell/tape/tape.ts`: import `TapeShock` and
`TapeFeed` (`'../../stores/tape-feed'`). Module level, below `proxyLabel`:

```ts
const NA = 'n/a';
const signed = (v: number, digits: number) => `${v >= 0 ? '+' : ''}${v.toFixed(digits)}`;
const atr = (v: number | null) => (v === null ? NA : `${signed(v, 2)} ATR`);

function sinceUtc(iso: string | null): string {
  const at = iso ? new Date(iso) : null;
  return at && !Number.isNaN(at.getTime()) ? ` since ${at.toISOString().slice(11, 16)} UTC` : '';
}

/** v210: the badge's tooltip -- label, since and the last reading's numbers. */
export function shockSummary(s: TapeShock): string {
  const vix = s.vix_missing || s.vix_level === null ? 'VIX missing'
    : `VIX ${s.vix_level.toFixed(2)} (${s.vix_chg_pct === null ? NA : `${signed(s.vix_chg_pct, 1)}%`})`;
  const sectors = s.sectors_down === null || s.sectors_total === null
    ? NA : `${s.sectors_down}/${s.sectors_total}`;
  return [
    `Market state ${s.label}${sinceUtc(s.since)}`,
    `breadth ${s.breadth_pct === null ? NA : `${s.breadth_pct.toFixed(0)}%`}`,
    `sectors ${sectors}`, `SPY ${atr(s.spy_atr_move)}`, `QQQ ${atr(s.qqq_atr_move)}`, vix,
  ].join(' · ');
}
```

In the class: `private readonly feed = inject(TapeFeed);`,
`protected readonly shock = this.feed.shock;`,
`protected readonly shockTitle = computed(() => { const s = this.shock(); return s ? shockSummary(s) : null; });`.
In the template, directly after the `.lane` div's closing `</div>`:

```html
    @if (shock(); as s) {
      <div class="shock-badge" role="status" [attr.data-label]="s.label"
           [attr.title]="shockTitle()" [attr.aria-label]="shockTitle()">
        <span class="shock-cap">state</span>
        <span class="shock-label">{{ s.label }}</span>
        @if (s.vix_missing) {
          <span class="shock-vix">VIX missing</span>
        }
      </div>
    }
```

2d. `frontend/src/app/shell/tape/tape.css`: add `flex-wrap: wrap;` to the
`:host` rule and `flex: 1 1 0%;` to the `.lane` rule (a zero basis keeps the
lane and badge on one line on desktop; the lane already shrinks to the host).
Append:

```css
/* v210: the market-shock badge. A sibling of .lane, never inside .viewport,
   so the tape's clip can never cut it: right of the tape from md (1024px),
   on its own line under the tape below that. */
.shock-badge { flex: none; display: flex; align-items: center; gap: var(--space-6);
               height: 32px; padding: 0 var(--space-10); white-space: nowrap;
               border-bottom: 1px solid var(--border); border-left: 1px solid var(--border);
               background: var(--surface); color: var(--text-muted);
               font-size: var(--text-micro); letter-spacing: .06em; text-transform: uppercase; }
.shock-label { font-weight: 650; color: var(--text-secondary); }
.shock-badge[data-label='SHOCK'] .shock-label { color: var(--neg); }
.shock-badge[data-label='RECOVERY'] .shock-label,
.shock-vix { color: var(--warn); }

@media (max-width: 1023px) {
  .lane { flex-basis: 100%; }
  .shock-badge { flex: 1 1 100%; height: 24px; border-left: none; }
}
```

- [ ] **Step 3: Run the frontend tests to verify they pass**

Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/stores/tape-feed.spec.ts`
Run: `node frontend/scripts/ng-test.mjs frontend --include src/app/shell/tape/tape.spec.ts`
Expected: PASS, every pre-existing test in both files included.

- [ ] **Step 4: Check the badge at 390, 820 and 1440 px**

1. `/replicate-prod-db`; then, with the environment `admin_ui.py` uses,
   `python -m alembic upgrade head` if the local database lacks
   `market_shock_state` (it carries `v209_001` from V209-5, v209 (merged)).
2. Seed one SHOCK state with a scratch script (scratchpad, not the repo):

```python
from datetime import datetime, timezone
from swingbot.core.db.repositories.market_shock import market_shock_repo
from swingbot.core.market import shock

now = datetime.now(timezone.utc)
reading = shock.ShockReading(
    as_of=now, session_date=now.date(), minutes_since_open=60.0, breadth_frac=0.42,
    sectors_down=5, sectors_total=8, breadth_speed=0.12, spy_atr_move=-1.8, qqq_atr_move=-2.3,
    spy_last=671.2, spy_prev_close=683.0, spy_session_low=670.9, spy_new_low=True,
    spy_retrace=0.05, vix_level=21.13, vix_chg_pct=27.2, vix_session_high=21.4,
    vix_off_high_pct=1.3, n_names=61, insufficient=False)
state = shock.ShockState(label="SHOCK", since=now, session_date=now.date())
print(market_shock_repo().record(reading.as_row(), state.as_row(), state_after="SHOCK"))
```

3. `cd <wt>/frontend && npm run build`, `cd <wt> && python admin_ui.py`, sign
   in with `node frontend/scripts/browse.mjs login --base http://localhost:1234`
   (`.env` admin credentials loaded inside the script, never printed).
4. `node frontend/scripts/layout-audit.mjs --base http://localhost:1234 --widths 390,820,1440`
   must exit 0. Findings on routes unrelated to the shell tape are listed in
   the report, not fixed here.
5. At most three clipped shots:
   `node frontend/scripts/browse.mjs shots --base http://localhost:1234 --path /dashboard --widths 1440,820 --clip "sb-tape"`.
   At 1440 the badge reads `STATE SHOCK` to the right of the moving tape on
   one line; at 820 it sits on its own line under the tape and the tape's
   tiles keep their full width. At 390 run the same command without `--clip`
   and read only the `.txt` (no image): `page-scroll-x: 0` (the shell hides
   the tape strip on phones, badge included).
6. Delete the seeded rows from the scratch script, same environment:
   `with get_engine().begin() as c:` run `c.execute(sa.delete(schema.market_shock_state))`
   and `c.execute(sa.delete(schema.market_shock_readings))`
   (`swingbot.core.db.engine.get_engine`, `swingbot.core.db.schema`).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app/api/models.ts frontend/src/app/stores/tape-feed.ts \
        frontend/src/app/stores/tape-feed.spec.ts frontend/src/app/shell/tape/tape.ts \
        frontend/src/app/shell/tape/tape.css frontend/src/app/shell/tape/tape.spec.ts
git commit -m "feat(v210): market-shock badge beside the shell tape"
```

---

# Phase 3 — release and close-out

### Task V210-4: Release: bot patch + ui patch, deploy, shadow checks for the notice path and the badge

**Model:** sonnet — a bump, its regeneration and read-only production checks; no migration and no production write, so nothing here needs a stop-or-go judgement on live data.

**Files:**
- Modify: `docs/deploy/DEPLOY_HETZNER.md` — one paragraph `v210: market-shock notice and tape badge` at the end of the `### v209: market shock tables` section (created by V209-13, v209 (merged))
- Modify: `VERSION.json` (`bot` patch, `ui` patch, both `*_updated` stamps)
- Modify: `swingbot/admin/version_history.json` (regenerated, never hand-edited)

**Interfaces:**
- Consumes: every task V210-1..V210-3b merged on `main` with CI green; plan v209 merged **and released** (its `release(bot): ... -- v209 market-shock detector (shadow)` commit present in `git log -- VERSION.json`, production `MARKET_SHOCK_MODE=shadow`, `market_shock_state` row 1 written by a stepped pass). `shock_notices.notice_payload`, `notice_event`, `FOOTER` (V210-1, V210-2); `lifecycle_notifications.build_lifecycle_notification(event)` rendering `market_shock` (V210-1b); `market_shock_repo().current_state()` / `.latest_reading()`, `ShockState.from_row`, `ShockReading.from_row` (V209-2..5b, v209 (merged)); `GET /api/v1/market/tape` → `shock` (V210-3); `.shock-badge[data-label]` (V210-3b).
- Produces: release commit `release(bot,ui): bot <B> / ui <U> -- market-shock notice and tape badge (v210)` and its regeneration commit `chore(bot,ui): bot <B> / ui <U> -- market-shock notice and tape badge (v210)`, which V210-5's double-bump guard looks for.

**Bump level (index `**Bump:**`): bot patch, ui patch.** A new Discord status notice and a new badge are "something someone might notice", the patch definition in `working-conventions.md` § The three levels; neither makes the bot or the admin UI something a user must look at anew (the minor test, used three times in the repo's life), and nothing needs a manual server step (major).

Rules for this task: production is reached **only** through `bash scripts/ops/ssh-hetzner.sh "<cmd>"` (stdin piped for scripts); `.env` values are never printed (count matches only). Every check below is read-only: **nothing is enqueued, nothing is posted to Discord**. A failed check is a stop: report `BLOCKED:` with the output to the controller; never fix forward on production. Any production change made anyway (a `.env` edit, a restart with a changed setting) is mirrored per `/mirror-prod` before this task counts as done.

- [ ] **Step 1: Preconditions — v209 released, v210 merged and green**

Run: `git log --oneline -- VERSION.json | head -5`
Expected: the v209 `release(bot): ... -- v209 market-shock detector (shadow)` commit is present and newer than `10c75111`. Missing → stop (`BLOCKED: v209 not released`).

Run: `git log --oneline main | grep -c "feat(v210)"`
Expected: `6` (V210-1, 1b, 2, 2b, 3, 3b).

Run: `gh run list --branch main --limit 1 --json databaseId,status,conclusion`
Expected: the newest run, which contains the last `feat(v210)` commit, is `completed` / `success`. Pending → `gh run watch <id> --exit-status` in the background first.

- [ ] **Step 2: Bump commit**

Read the current pair: `python -c "import json;v=json.load(open('VERSION.json'));print(v['bot'],v['ui'])"`.
Set `bot` to its patch successor (`x.y.z` → `x.y.(z+1)`, each part an integer) and `ui` to its patch successor; set `bot_updated` and `ui_updated` to the same UTC stamp from `date -u '+%Y-%m-%d %H-%M-%S'`. Touch no other key.

```bash
git add VERSION.json
git commit -m "release(bot,ui): bot <B> / ui <U> -- market-shock notice and tape badge (v210)"
```

(`<B>`, `<U>` are the two new versions, written out.)

- [ ] **Step 3: Regenerate the version history, then test it**

Run: `python scripts/dev/build_version_matrix.py`
Run: `python scripts/dev/testrun.py file tests/scripts/test_build_version_matrix.py`
Expected: `0 failed`; `git diff --stat` shows only `swingbot/admin/version_history.json`, and its `current` pair equals the new `VERSION.json` pair with the release commit's sha (never `"uncommitted"`).

- [ ] **Step 4: Deploy note in `DEPLOY_HETZNER.md`, commit, push**

Append to the end of the `### v209: market shock tables` section:

```markdown
**v210: market-shock notice and tape badge.** No revision, no new setting:
a stepped pass that changes the market state enqueues one `market_shock`
event in the v197 notify queue (`manual_close_notify`), delivered as a plain
status embed to `DISCORD_CHANNEL_OPS_ID` (falls back to the trades channel);
`GET /api/v1/market/tape` carries a `shock` object and the shell tape shows
a NORMAL / SHOCK / RECOVERY badge at 640 px and wider. `MARKET_SHOCK_MODE=off`
silences both (no reading, no notice, `shock: null`). Rollback is image-only
(§ Rolling back): the previous image does not know the third queue kind, so
after a rollback check
`SELECT count(*) FROM manual_close_notify WHERE delivered_at IS NULL AND doc::text LIKE '%market_shock%'`
and, if it is not `0`, ask before deleting those rows.
```

```bash
git add swingbot/admin/version_history.json docs/deploy/DEPLOY_HETZNER.md
git commit -m "chore(bot,ui): bot <B> / ui <U> -- market-shock notice and tape badge (v210)"
git push origin main
```

- [ ] **Step 5: Watch the pipeline through the deploy**

Run: `gh run list --branch main --limit 1 --json databaseId,status,conclusion`, then `gh run watch <id> --exit-status` (background).
Expected: green through the `deploy` job. A failing unit test: fix it alone (`testrun.py file ...`), commit scoped, push, watch again (`working-conventions.md` § Pipeline watch). A failing deploy job: stop and report; never retry a deploy blindly.

Then: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && cat VERSION.json"`
Expected: the new `bot` / `ui` pair. Record the deploy time (UTC) from the run.

- [ ] **Step 6: Production is still in `shadow`, and a notice builds and renders**

Run: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && grep -c '^MARKET_SHOCK_MODE=shadow$' .env"`
Expected: `1`. (`0` → stop; never edit `.env` from this task.)

Write `$SCRATCH/v210_notice_dry.py` (scratchpad, not the repo):

```python
"""v210 release check: build and render a market_shock notice from production's
stored state without enqueueing or posting anything."""
from datetime import datetime, timezone

from swingbot import config
from swingbot.core.db.repositories.market_shock import market_shock_repo
from swingbot.core.market import shock
from swingbot.core.scanning import lifecycle_notifications, shock_notices

repo = market_shock_repo()
state_row, reading_row = repo.current_state(), repo.latest_reading()
assert state_row is not None and reading_row is not None, "no stepped pass stored yet"
prior = shock.ShockState.from_row(state_row["doc"]["state"])
now = datetime.now(timezone.utc)
target = shock.SHOCK if prior.label != shock.SHOCK else shock.RECOVERY
new = shock.ShockState(label=target, since=now)
reading = shock.ShockReading.from_row(
    {k: v for k, v in reading_row.items() if k not in ("id", "state_after")})
payload = shock_notices.notice_payload(prior, new, reading, [], now)
event = shock_notices.notice_event(payload, as_of=now)   # make_event validates
embed = lifecycle_notifications.build_lifecycle_notification(event)
desc = embed.description or ""
print("channel_set", bool(config.DISCORD_CHANNEL_OPS_ID or config.DISCORD_CHANNEL_TRADES_ID))
print("kind", event["kind"], "label", payload["label"], "prior", payload["prior_label"])
print("title", embed.title)
print("desc_len", len(desc), "footer_ok", target != shock.SHOCK or shock_notices.FOOTER in desc)
```

Run: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T bot python -" < "$SCRATCH/v210_notice_dry.py"`
Expected: `channel_set True`; `kind market_shock`; a title `Market state: <prior> → <new>`; `desc_len` > 0 and ≤ 4096; `footer_ok True`. Any traceback → stop and report. The script writes nothing (no `record()`, no `enqueue`).

- [ ] **Step 7: Queue and state rows since the deploy**

Write `$SCRATCH/v210_queue.sql`:

```sql
SELECT label, since, last_notice_at, updated_at FROM market_shock_state WHERE id = 1;
SELECT count(*) AS readings_since_deploy FROM market_shock_readings WHERE as_of > '<deploy time UTC>';
SELECT count(*) AS shock_events, count(delivered_at) AS delivered
  FROM manual_close_notify WHERE doc::text LIKE '%market_shock%';
```

Run: `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose exec -T db psql -U swingbot -d swingbot" < "$SCRATCH/v210_queue.sql"`
Expected: one state row; `readings_since_deploy > 0` when the check runs in NYSE regular hours at least 30 minutes after the deploy (outside hours: record `pending`, re-check on the next session before V210-5); `shock_events = delivered` (a transition since the deploy delivered its notice; `0 / 0` is the normal case on a calm day). `shock_events > delivered` for more than 10 minutes → read `bash scripts/ops/ssh-hetzner.sh "cd /opt/swing-bot && docker compose logs --since 30m bot" | grep -i "notify\|market_shock"` and stop.

- [ ] **Step 8: The tape API and the badge on production**

Run: `node frontend/scripts/browse.mjs api --base https://bomeo-capital.com --path "/api/v1/market/tape"` (signs in with `.env`'s `ADMIN_USERNAME`/`ADMIN_PASSWORD` inside the script; never print them)
Expected: a `shock` object whose `label` equals Step 7's state label and whose keys are exactly `label, since, as_of, breadth_pct, sectors_down, sectors_total, spy_atr_move, qqq_atr_move, vix_level, vix_chg_pct, vix_missing`.

Run: `node frontend/scripts/browse.mjs shots --out "$SCRATCH/v210_shots" --base https://bomeo-capital.com --path "/dashboard" --widths 1440,820,390 --clip ".tape-strip"`
Expected (read the clipped PNGs and their `.txt`): at 1440 px the badge sits to the tape's right with the stored label; at 820 px it wraps onto its own line under the tape; at 390 px the tape strip is hidden by the shell (no badge — the index's OPEN item); horizontal page scroll `0` at every width.

- [ ] **Step 9: Mirror and report**

No production change is expected from this task. If one was made (any `.env` edit or restart with a changed value), run `/mirror-prod` and commit the mirror (`.env.example` / `DEPLOY_HETZNER.md`) before reporting. Report to the controller: the new pair, the deploy run id, Steps 6–8 verdicts, and any `pending` item (Step 7 outside hours) for V210-5 to re-check.

### Task V210-5: `/panel` (veteran-trader, senior-engineer, financial-advisor) + `/close-out` without a second bump

**Model:** sonnet — runs two skills in order and follows their findings; the only judgement is the double-bump guard, which is a fixed `git log` check.

**Files:**
- Modify (moved by `/close-out`): `docs/superpowers/plans/2026-11-06-v210-market-shock-notices-and-badge_0-index.md`, `..._1-notices.md`, `..._2-admin-badge.md` → `docs/superpowers/plans/implemented/`
- Not modified: `VERSION.json`, `swingbot/admin/version_history.json` (released in V210-4), the v209 spec (it stays in `specs/`; the Track 2 plan closes it)

**Interfaces:**
- Consumes: V210-4's `release(bot,ui): bot <B> / ui <U> -- market-shock notice and tape badge (v210)` commit and its `chore(bot,ui)` regeneration commit; V210-4's report (any `pending` Step 7 item).
- Produces: none (last task).

- [ ] **Step 1: Close any `pending` production check**

If V210-4 reported Step 7 `pending`, re-run its SQL in NYSE regular hours (same command, same expectations) and record the result in the V210-4 report thread. A failure here is a stop: report `BLOCKED:` before any panel.

- [ ] **Step 2: `/panel` over the merged v210 diff**

Run: `git log --format=%h --grep="(v210)" main | tail -1` → the first v210 commit `<first>`; the target is `git diff <first>^..main -- swingbot frontend tests docs/deploy`.
Invoke `/panel veteran-trader,senior-engineer,financial-advisor <that diff>` — veteran-trader on the notice's content at a shock (is the open-long list what a trader needs, is `THROUGH STOP` read right), senior-engineer on the queue kind beside the two untouched kinds, the stepped-pass hook and the three-width badge, financial-advisor on notice frequency (the rate limit) and how open R and risk are shown.
Each finding is fixed in its own scoped commit with its test (`testrun.py file <test>`, never the full suite), pushed, and the CI run watched green, or recorded as declined with the reason in the close-out commit message. A finding that would change shadow into a trade change is out of scope: record it for the Track 2 / live spec, never fix it here.

- [ ] **Step 3: Double-bump guard**

Run: `git log --oneline -- VERSION.json | head -3`
Expected: V210-4's `release(bot,ui): ... (v210)` commit is listed (newest, unless another plan released since), and `VERSION.json` holds `<B>` / `<U>` or a later pair. Present → the bump is already released: tell `/close-out` so, so its Steps 3–4 (resolve and apply the bump, regenerate) are skipped and Step 5's prediction check still runs. Missing → stop and report; **never bump here**.

- [ ] **Step 4: `/close-out`**

Invoke `/close-out` for plan v210. It moves the three v210 plan files to `docs/superpowers/plans/implemented/` and removes the plan's worktree. The close-out commit message records `bump released in V210-4 (<sha of the release commit>)`, the panel verdict per role, and any declined finding.

Run: `ls docs/superpowers/plans/implemented/ | grep -c "v210-market-shock-notices-and-badge"`
Expected: `3`. Then `git push origin main` and watch the run green (`working-conventions.md` § Pipeline watch).
