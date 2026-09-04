# v71 — Silent-failure hardening, part 1: the crash and its isolation

> **Part of a split plan.** The header block, Global Constraints and the
> cross-part map live in `2026-09-04-v71-silent-failure-hardening_0-index.md`.
> Read that first — this file carries only its phases.

# Phase A — The crash and its twin

Three call sites format a nullable metric. One crashes in production nightly,
one is latent, one is guarded only by a dict-existence check.

## Parallelisation

- **Group 1 (parallel):** H1, H2, H3 — one source file each
  (`retrospective.py`, `insights.py`, `analyze.py`), one test file each, no
  shared symbol introduced by any of them.
- **Sequential:** nothing within this phase. Phase B's H4 must follow H1
  (both edit `build_daily_retrospective`).

### Task H1: Guard the daily retrospective's calibration line

Reproduces and fixes the live production crash.

**Files:**
- Modify: `swingbot/core/tracking/retrospective.py:609-613`
- Test: `tests/tracking/test_retrospective_v2.py`

**Interfaces:**
- Consumes: `calibration.level_calibration(closed) -> list[dict]` with keys
  `level`, `n`, `win_rate`, `expectancy_r`; `win_rate` is `float | None`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/tracking/test_retrospective_v2.py`:

```python
import datetime as dt


def _manual_close(ticker, level, closed_at):
    """A trade closed manually -- status is neither 'win' nor 'loss', so it
    counts toward level_calibration()'s n but contributes nothing to
    metrics.win_rate(), which then returns None."""
    return {"ticker": ticker, "status": "closed", "confidence_level": level,
            "opened_at": "2026-09-03T08:00:00+00:00", "closed_at": closed_at,
            "direction": "bullish", "entry": 100.0, "stop_loss": 95.0,
            "exit_price": 101.0}


def test_retrospective_survives_a_level_with_only_manual_closes(tmp_path, monkeypatch):
    from swingbot.core.tracking import retrospective as retro

    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))
    trades = [_manual_close("AAPL", 3, "2026-09-03T18:00:00+00:00")]

    messages = retro.build_daily_retrospective(trades, today=dt.date(2026, 9, 3))

    joined = "\n".join(messages)
    assert "Level 3" in joined
    assert "n/a" in joined          # rendered, not dropped and not "0%"
    assert "0% WR" not in joined    # None must never render as zero
```

- [ ] **Step 2: Run the test and confirm it fails for the right reason**

Run: `python -m pytest tests/tracking/test_retrospective_v2.py::test_retrospective_survives_a_level_with_only_manual_closes -v`

Expected: **FAIL** with `TypeError: unsupported format string passed to
NoneType.__format__` at `retrospective.py:612`. This is the exact production
traceback. If it fails any other way, stop and investigate — the fixture is not
reaching the calibration path.

- [ ] **Step 3: Fix the format site**

In `swingbot/core/tracking/retrospective.py`, replace the loop at 609-613:

```python
        calibration_lines.append("**📐 Calibration**")
        for r in level_rows:
            wr = f"{r['win_rate']:.0f}%" if r["win_rate"] is not None else "n/a"
            calibration_lines.append(
                f"• Level {r['level']} at {wr} WR (n={r['n']})."
            )
```

Keep the `if r["n"] > 0` row filter as-is: it is the correct filter for *which
rows to show*. It was only ever wrong as a guard for *whether the value is
formattable*.

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python -m pytest tests/tracking/test_retrospective_v2.py::test_retrospective_survives_a_level_with_only_manual_closes -v`
Expected: **PASS**

- [ ] **Step 5: Run the file's whole suite for regressions**

Run: `python scripts/dev/testrun.py file tests/tracking/test_retrospective_v2.py`
Expected: `VERDICT: PASS`

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/tracking/retrospective.py tests/tracking/test_retrospective_v2.py
git commit -m "fix(v71): render an incomputable level win rate as n/a, not a crash"
```

### Task H2: Guard the weekly digest's calibration line

The same defect, copy-pasted, over a weekly window.

**Files:**
- Modify: `swingbot/core/analytics/insights.py:88-92`
- Test: `tests/analytics/test_insights.py`

**Interfaces:**
- Consumes: `insights.weekly_digest(entries, closed, today) -> list[str]`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/analytics/test_insights.py` (the module already defines
`TODAY = dt.date(2026, 3, 8)` and imports `weekly_digest`):

```python
def _manual_closed(closed_at, level):
    """Closed inside the digest window but with no win/loss verdict."""
    return {"status": "closed", "closed_at": closed_at, "direction": "bullish",
            "entry": 100.0, "stop_loss": 95.0, "exit_price": 101.0,
            "realized_pnl_amount": 10.0, "confidence_level": level}


def test_weekly_digest_survives_a_level_with_only_manual_closes():
    closed = [_manual_closed("2026-03-04T10:00:00+00:00", 3)]
    entries = [_entry("aaa", 0.2, "2026-03-04T10:00:00+00:00", [])]

    messages = weekly_digest(entries, closed, TODAY)

    joined = "\n".join(messages)
    assert "Lv3" in joined
    assert "n/a" in joined
    assert "Lv3: 0%" not in joined
```

- [ ] **Step 2: Run the test and confirm it fails for the right reason**

Run: `python -m pytest tests/analytics/test_insights.py::test_weekly_digest_survives_a_level_with_only_manual_closes -v`

Expected: **FAIL** with `TypeError: unsupported format string passed to
NoneType.__format__` at `insights.py:92`.

- [ ] **Step 3: Fix the format site**

In `swingbot/core/analytics/insights.py`, replace the join at 90-92:

```python
        lines.append("**Confidence-level calibration:** " + " · ".join(
            f"Lv{r['level']}: "
            f"{f'{r['win_rate']:.0f}%' if r['win_rate'] is not None else 'n/a'} "
            f"(n={r['n']})"
            for r in level_rows
        ))
```

If the nested quoting reads badly, use an explicit loop instead — same
behaviour, and clearer:

```python
        parts = []
        for r in level_rows:
            wr = f"{r['win_rate']:.0f}%" if r["win_rate"] is not None else "n/a"
            parts.append(f"Lv{r['level']}: {wr} (n={r['n']})")
        lines.append("**Confidence-level calibration:** " + " · ".join(parts))
```

Prefer the explicit loop. It matches `trades.py:390` and reads at a glance.

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python -m pytest tests/analytics/test_insights.py::test_weekly_digest_survives_a_level_with_only_manual_closes -v`
Expected: **PASS**

- [ ] **Step 5: Run the file's whole suite for regressions**

Run: `python scripts/dev/testrun.py file tests/analytics/test_insights.py`
Expected: `VERDICT: PASS`

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/analytics/insights.py tests/analytics/test_insights.py
git commit -m "fix(v71): guard the weekly digest's level win rate the same way"
```

### Task H3: Guard the scan badge-stats line

Lower severity — it sits inside a `try/except` so it degrades rather than
crashes — but the guard is still checking the wrong thing.

**Files:**
- Modify: `swingbot/core/scanning/analyze.py:188-189`
- Test: `tests/scanning/test_embeds_badges.py`

**Interfaces:**
- Consumes: `plan.badge_stats` — a `dict | None` with keys `n`, `win_rate`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing test**

Append to `tests/scanning/test_embeds_badges.py`:

```python
def test_badge_stats_with_null_win_rate_does_not_raise():
    """badge_stats exists but carries no computable win rate -- the current
    guard only checks that the dict is present, so it formats None."""
    from swingbot.core.scanning import analyze

    stats = {"n": 4, "win_rate": None}
    rendered = analyze._format_badge_stats(stats)

    assert "N=4" in rendered
    assert "n/a" in rendered
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `python -m pytest tests/scanning/test_embeds_badges.py::test_badge_stats_with_null_win_rate_does_not_raise -v`

Expected: **FAIL** with `AttributeError: module ... has no attribute
'_format_badge_stats'` — the helper does not exist yet.

- [ ] **Step 3: Extract and guard the helper**

In `swingbot/core/scanning/analyze.py`, add above `_scan_one`:

```python
def _format_badge_stats(stats: dict | None) -> str:
    """The badge's out-of-sample record, or "" when there is no record.

    win_rate is None whenever the registry entry has no computable rate;
    formatting it directly is the defect this exists to prevent.
    """
    if not stats:
        return ""
    wr = f"{stats['win_rate']:.1f}% OOS" if stats.get("win_rate") is not None else "n/a OOS"
    return f"N={stats['n']} · {wr}"
```

Then replace the inline expression at 188-189:

```python
            "badge_stats": _format_badge_stats(getattr(plan, "badge_stats", None)),
```

- [ ] **Step 4: Run the test and confirm it passes**

Run: `python -m pytest tests/scanning/test_embeds_badges.py::test_badge_stats_with_null_win_rate_does_not_raise -v`
Expected: **PASS**

- [ ] **Step 5: Run the file's whole suite for regressions**

Run: `python scripts/dev/testrun.py file tests/scanning/test_embeds_badges.py`
Expected: `VERDICT: PASS`

- [ ] **Step 6: Commit**

```bash
git add swingbot/core/scanning/analyze.py tests/scanning/test_embeds_badges.py
git commit -m "fix(v71): guard badge_stats win rate on the value, not the dict"
```

---

# Phase B — Contain the blast radius

## Parallelisation

Sequential throughout, and after Phase A's H1: H4 edits the same function H1
edits, and the wrapper must go around already-correct code so a failure in its
test means the wrapper rather than the formatting.

### Task H4: Isolate each retrospective part

**Files:**
- Modify: `swingbot/core/tracking/retrospective.py:446-672`
- Test: `tests/tracking/test_retrospective_v2.py`

**Interfaces:**
- Produces: `retrospective._section(name: str, failures: list[str])` — a
  `contextlib.contextmanager` used only inside this module.

- [ ] **Step 1: Write the failing test**

Append to `tests/tracking/test_retrospective_v2.py`:

```python
def test_one_failing_section_does_not_lose_the_whole_report(tmp_path, monkeypatch, caplog):
    """A raise inside one part must cost that part only. Before isolation,
    it aborted all ten parts and the report never posted."""
    from swingbot.core.tracking import retrospective as retro

    monkeypatch.setattr(retro, "_HISTORY_PATH", str(tmp_path / "history.json"))

    def _boom(*a, **kw):
        raise RuntimeError("calibration exploded")

    monkeypatch.setattr(retro.calibration, "level_calibration", _boom)
    trades = [_manual_close("AAPL", 3, "2026-09-03T18:00:00+00:00")]

    with caplog.at_level("ERROR"):
        messages = retro.build_daily_retrospective(trades, today=dt.date(2026, 9, 3))

    joined = "\n".join(messages)
    assert "Daily Retrospective" in joined          # Part 1 still posted
    assert "calibration" in joined.lower()          # the degraded notice names it
    assert any("calibration" in r.message for r in caplog.records)
```

- [ ] **Step 2: Run the test and confirm it fails for the right reason**

Run: `python -m pytest tests/tracking/test_retrospective_v2.py::test_one_failing_section_does_not_lose_the_whole_report -v`

Expected: **FAIL** with `RuntimeError: calibration exploded` escaping
`build_daily_retrospective` — proving the current no-isolation behaviour.

- [ ] **Step 3: Add the context manager**

At the top of `swingbot/core/tracking/retrospective.py`, add `import contextlib`
to the existing imports. Then add above `build_daily_retrospective`:

```python
@contextlib.contextmanager
def _section(name: str, failures: list[str]):
    """Isolate one part of the retrospective.

    A part that raises contributes nothing and is named in `failures`; the
    remaining parts still post. Generalises the guards that already existed
    around get_daily_summary() and edge_decay_report().

    A context manager rather than an extracted function per part: the parts
    read ~15 locals computed in the partition block above them, and a `with`
    block keeps those in scope where extraction would have to thread them all
    through new signatures.
    """
    try:
        yield
    except Exception:
        log.exception("build_daily_retrospective: %s section failed, skipping", name)
        failures.append(name)
```

- [ ] **Step 4: Wrap each part**

In `build_daily_retrospective`, after `messages: list[str] = []` (line 446) add:

```python
    failed_sections: list[str] = []
```

Then indent each of the ten part bodies one level under a `with`, using these
exact names (the test asserts on `calibration`):

| Part | Line marker today | `_section` name |
|---|---|---|
| 1 | `── Part 1: Header + at-a-glance` | `header` |
| 2 | `── Part 2: Closed-today trade table` | `closed trades` |
| 3 | `── Part 3: Still-open positions` | `open positions` |
| 4 | `── Part 4: Breakdown tables` | `breakdowns` |
| 5 | `── Part 5: Lessons learned` | `lessons` |
| 6 | `── Part 6: Calibration + edge decay` | `calibration` |
| 7 | `── Part 7: Journal lessons` | `journal` |
| 8 | `── Part 8: Weekly risk report` | `weekly risk` |
| 9 | `── Part 9: RS rotation report` | `rs rotation` |
| 10 | `── Part 10: Scan health alarm` | `scan health` |

Each becomes, e.g.:

```python
    # ── Part 6: Calibration + edge decay (analytics core) ─────────────────
    with _section("calibration", failed_sections):
        calibration_lines = []
        ...existing body, indented one level...
        if calibration_lines:
            messages.append("\n".join(calibration_lines))
```

**Do not wrap the partition block (lines 397-444).** If partitioning fails there
is no report to build at all, and `daily_recap`'s own handler is the right place
for that. Leave the two pre-existing inner `try/except` guards
(`get_daily_summary`, `edge_decay_report`) exactly where they are — they are
finer-grained than the section guard and still useful.

- [ ] **Step 5: Append the degraded-report notice**

Immediately before `return messages` (line 672):

```python
    if failed_sections:
        messages.append(
            "⚠️ _Some sections of this report failed to build and were skipped: "
            + ", ".join(failed_sections)
            + ". See the bot log for the traceback._"
        )
    return messages
```

A degraded report must look degraded. Silently shipping a short report is how a
missing section goes unnoticed — the same failure mode this whole plan exists
to close.

- [ ] **Step 6: Run the test and confirm it passes**

Run: `python -m pytest tests/tracking/test_retrospective_v2.py::test_one_failing_section_does_not_lose_the_whole_report -v`
Expected: **PASS**

- [ ] **Step 7: Run the file's whole suite for regressions**

Run: `python scripts/dev/testrun.py file tests/tracking/test_retrospective_v2.py`
Expected: `VERDICT: PASS`

If a later part now fails because it referenced a local an earlier part defines,
that is a genuine cross-part coupling the isolation exposed. Fix it by hoisting
that local above the `with` blocks — do not widen a section to hide it.

- [ ] **Step 8: Commit**

```bash
git add swingbot/core/tracking/retrospective.py tests/tracking/test_retrospective_v2.py
git commit -m "fix(v71): isolate each retrospective section so one failure costs one section"
```
