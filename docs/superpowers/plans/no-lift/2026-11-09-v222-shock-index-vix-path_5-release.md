# v222 — Market-shock detector: index + VIX entry path — Part 5: production check, Stage 3, release

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [`docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md`](../specs/2026-11-09-v222-shock-index-vix-path-design.md) (§ Stages: Stage 3, § Acceptance production check, § Config)
**Index:** [`2026-11-09-v222-shock-index-vix-path_0-index.md`](2026-11-09-v222-shock-index-vix-path_0-index.md) — Goal, Global Constraints, Parallelisation and the task ledger live there; every task below implicitly includes them.

Tasks V222-12, V222-13, V222-14: the read-only production check, the two
Stage 3 reports (2026-11-05 in-sample on real one-minute `^VIX`, and the 26 A1
days on ramp VIX), gate 3, and the release that makes the frozen cell the
config `Field` default.

**Start condition.** Gate 2 passed: Results § Stage 2 carries the line
`**Frozen cell: FROZEN_K = <k>, FROZEN_V = <v>.**`. On a NO-LIFT at gate 1 or
gate 2 this part is never run. V222-12 may run beside V222-9..V222-11;
V222-13 needs V222-9 (the real `_index_path` inside `shock.step`), V222-6d (the
vix1m fixture) and V222-8; V222-14 runs last, after gate 3.

**Rules every task here keeps (index § Global Constraints, restated because
they decide review):**

- Nothing in this part re-opens a frozen rule. The Stage 3 reports are
  descriptive: they never gate and are never cited as corroboration for the
  release. Gate 3 approves a release; it does not re-score Stage 2.
- `ShockThresholds()` stays `index_atr_k = 0.0`, `index_vix_chg = 0.0`.
  `tests/market/test_shock_acceptance_a1.py`, `tests/fixtures/shock_replay/`
  and `tests/fixtures/shock_replay_2026_11_05.json` are never edited; the A1
  test prints the same report after V222-14 as on `main` before v222.
- Production is read-only here (`bash "$M/scripts/ops/ssh-hetzner.sh"`). No
  `.env` value (local or production) is ever printed: the key check prints
  match counts only. No deploy, no VM edit inside the plan.

**Paths used in every task.**

```bash
M=E:/Documents/Private/Projects/Discord-Bot                                   # main tree
W=$M/.claude/worktrees/2026-11-09-v222-shock-index-vix-path                   # worktree (all code)
D=$M/data/v222                                                                 # stage data (gitignored, main tree)
SPEC=$M/docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
```

Read the frozen cell once per task (never retype it by hand):

```bash
python - "$SPEC" <<'PYEOF'
import re, sys
from pathlib import Path
m = re.search(r"\*\*Frozen cell: FROZEN_K = ([0-9.]+), FROZEN_V = ([0-9.]+)\.\*\*",
              Path(sys.argv[1]).read_text(encoding="utf-8"))
assert m, "no frozen cell in Results: gate 2 has not passed, stop"
k, v = float(m.group(1)), float(m.group(2))
assert k in (1.0, 1.25, 1.5, 2.0) and v in (10.0, 15.0, 20.0, 25.0), (k, v)
print(f"K={k} V={v}")
PYEOF
```

`scripts/dev/testrun.py` resolves test paths against its own checkout, so
`python "$W/scripts/dev/testrun.py" file tests/...` runs the worktree's tests.
Never `cd`; use `git -C "$W"` and absolute paths. No test in this part reaches
Postgres, so no `/replicate-prod-db` run is needed.

# Phase 5 — Production check, Stage 3 and release

### Task V222-12: Production check (read-only): `^VIX` tape, staleness, lag, `spy_atr_move` nulls, explicit keys, shadow fire rate

**Model:** sonnet — a read-only report with small pure functions and exact tests; printing a `.env` value is avoided by counting matches only.

**Files:**
- Create: `scripts/reports/shock_vix_check.py`
- Create: `tests/scripts/test_shock_vix_check.py` (suite `tooling`)
- Modify (main tree, spec): `## Results` § Production check

**Interfaces:**
- Consumes: the frozen cell; `data/v222/stage1.json` (V222-5). In production only: `tape.read_tape` (`TapeEntry`), `get_engine()`, `load_watchlist()`, `config.BATCH_FETCH_CHUNK_SIZE`, `config.MARKET_REGIME_TICKER`; `market_shock_readings` (`doc` = `ShockReading.as_row()`); the VM's archive `market_data/vix/intraday_1m/VIX_<day>_1m.csv` (`scripts/ops/archive_vix.py`).
- Produces: `ENV_KEYS`, `COVERAGE_SQL`, `tape_status(entry, now, max_age_s=600)`, `coverage(rows, max_age_s=600)`, `read_archive_1m(paths)`, `lag_points(rows, vix_1m)`, `shadow_fire_rate(rows, k, v)`, `stage1_rate(stage1, k, v)`, `chunk_room(n, chunk_size, benchmark_in_watchlist)`, `env_presence(counts)`; Results § Production check, which gate 3 and V222-14 read.

- [ ] **Step 1: Write the failing tests**

Create `tests/scripts/test_shock_vix_check.py`:

```python
"""v222 V222-12: the production check's pure halves (no network, no database)."""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "reports") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "reports"))

import shock_vix_check as chk  # noqa: E402

NOW = datetime(2026, 11, 12, 15, 30, tzinfo=timezone.utc)


def _entry(age_s=60, proxy=False, price=18.0):
    return {"price": price, "change_pct": 5.0, "is_proxy": proxy,
            "proxy_symbol": "VIXY" if proxy else None,
            "as_of": (NOW - timedelta(seconds=age_s)).isoformat()}


def _row(minute, day="2026-11-12", spy=-0.2, vix=3.0, ins=False, level=18.0, state="NORMAL"):
    at = datetime.fromisoformat(f"{day}T14:30:00+00:00") + timedelta(minutes=minute)
    return {"as_of": at.isoformat(), "session_date": day, "state_after": state,
            "spy_atr_move": spy, "vix_level": level, "vix_chg_pct": vix, "insufficient": ins,
            "minutes_since_open": float(minute)}


def test_a_fresh_non_proxy_row_is_usable():
    s = chk.tape_status(_entry(), NOW)
    assert s["present"] and s["fresh"] and s["usable"] and not s["proxy"]
    assert s["age_s"] == pytest.approx(60.0)


@pytest.mark.parametrize("entry, key, value", [
    (None, "present", False), (_entry(proxy=True, price=None), "proxy", True),
    (_entry(age_s=601), "fresh", False), (_entry(price=None), "has_level", False)])
def test_missing_proxy_stale_or_levelless_rows_are_not_usable(entry, key, value):
    s = chk.tape_status(entry, NOW)
    assert s["usable"] is False and s[key] is value


def test_coverage_counts_nulls_per_row_and_sessions():
    rows = [_row(15), _row(30, vix=None, level=None), _row(45, spy=None),
            _row(15, day="2026-11-13", ins=True, state="SHOCK")]
    c = chk.coverage(rows)
    assert (c["rows"], c["sessions"], c["first"], c["last"]) == (4, 2, "2026-11-12", "2026-11-13")
    assert (c["vix_null"], c["spy_null"], c["insufficient"], c["shock_rows"]) == (1, 1, 1, 1)
    assert c["vix_null_rate"] == 0.25 and c["max_age_s"] == 600
    assert chk.coverage([])["vix_null_rate"] is None


@pytest.mark.parametrize("rows, k, fired", [
    ([_row(15, spy=-1.5, vix=20.0), _row(30, spy=-2.0, vix=25.0)], 1.5, 1),   # boundary
    ([_row(15, spy=-2.0, vix=25.0), _row(30, spy=-1.0, vix=25.0)], 1.5, 0),   # streak broken
    ([_row(15, spy=-2.0, vix=19.9), _row(30, spy=-2.0, vix=25.0)], 1.5, 0),   # VIX bar missed
    ([_row(15, spy=-2.0, vix=25.0), _row(30, ins=True), _row(45, spy=-2.0, vix=25.0)], 1.5, 1),
    ([_row(10, spy=-2.0, vix=25.0), _row(15, spy=-2.0, vix=25.0)], 1.5, 0),   # unsettled
    ([_row(15, spy=-2.0, vix=None), _row(30, spy=-2.0, vix=None)], 1.5, 0),   # no VIX
    ([_row(15, spy=-3.0, vix=50.0), _row(30, spy=-3.0, vix=50.0)], 0.0, 0),   # k = 0: off
])
def test_the_shadow_fire_rate_replays_the_two_reading_streak(rows, k, fired):
    r = chk.shadow_fire_rate(rows, k, 20.0)
    assert r["sessions_fired"] == fired and r["sessions"] == 1


def test_the_archive_reads_back_and_lag_uses_the_bar_finished_at_that_minute(tmp_path):
    path = tmp_path / "VIX_2026-11-12_1m.csv"
    path.write_text("Datetime,Adj Close,Close,High,Low,Open,Volume\n"
                    "2026-11-12 15:19:00+00:00,23.15,23.15,23.2,23.1,23.1,0\n"
                    "2026-11-12 15:20:00+00:00,23.3,23.3,23.4,23.2,23.2,0\n", encoding="utf-8")
    vix = chk.read_archive_1m([path, tmp_path / "missing.csv"])
    assert list(vix.values) == [23.15, 23.3]
    rows = [_row(50.5, level=21.13), _row(52, level=21.0), _row(50.5, level=None)]
    (p,) = chk.lag_points(rows, vix)                  # 15:20:30 reads the 15:19 bar
    assert p["lag_points"] == pytest.approx(21.13 - 23.15) and p["index"] == 23.15
    assert chk.read_archive_1m([]).empty


@pytest.mark.parametrize("n, size, has, room, quoted", [
    (100, 100, False, 0, False), (99, 100, False, 1, True), (100, 100, True, 0, True)])
def test_spy_is_quoted_only_with_chunk_room_or_on_the_watchlist(n, size, has, room, quoted):
    c = chk.chunk_room(n, size, has)
    assert (c["room"], c["benchmark_quoted"]) == (room, quoted)


def test_the_report_names_a_proxy_only_tape_and_both_rates():
    stage1 = {"window": {"sessions": 1000},
              "cells": [{"k": 1.5, "v": 20.0, "upper_fires": 30, "upper_episodes": 12}]}
    dump = {"now": NOW.isoformat(), "tape": _entry(proxy=True, price=None),
            "rows": [_row(15), _row(30)], "lag": [], "benchmark_is_spy": True,
            "chunk": chk.chunk_room(99, 100, False)}
    report = chk.build_report(dump, stage1, 1.5, 20.0, {"SHOCK_INDEX_VIX_CHG": 1})
    assert report["stage1"]["rate"] == 0.03 and report["shadow"]["sessions_fired"] == 0
    md = chk.render_md(report)
    assert report["env"] == {"SHOCK_INDEX_ATR_K": False, "SHOCK_INDEX_VIX_CHG": True}
    assert "can never fire" in md and "SHOCK_INDEX_VIX_CHG: explicit" in md
    assert "Stage 1 upper-bound rate" in md and "no archived one-minute" in md
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_vix_check.py
```

Expected: FAIL at collection, `ModuleNotFoundError: No module named 'shock_vix_check'`.

- [ ] **Step 3: Implement**

Create `scripts/reports/shock_vix_check.py`:

```python
#!/usr/bin/env python3
"""v222 V222-12: production check for the index path. Read-only.

No arguments: the dump, run inside production's bot container (piped over ssh;
the branch is not deployed). It prints ONE JSON line, writes nothing and prints
no .env value. --dump-json: the local report (markdown for Results).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ENV_KEYS = ("SHOCK_INDEX_ATR_K", "SHOCK_INDEX_VIX_CHG")
VIX_SYMBOL = "^VIX"
EPS = 1e-9
SETTLE_MIN = 15.0              # ShockThresholds().open_settle_min
COVERAGE_SQL = (
    "SELECT as_of, session_date, state_after, spy_atr_move, vix_level, vix_chg_pct, "
    "insufficient, (doc->>'minutes_since_open')::float AS minutes_since_open "
    "FROM market_shock_readings ORDER BY as_of, id")


def _ts(value) -> datetime | None:
    if value in (None, ""):
        return None
    t = datetime.fromisoformat(value) if isinstance(value, str) else value
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def _rate(n: int, d: int) -> float | None:
    return None if d == 0 else n / d


def tape_status(entry: dict | None, now: datetime, max_age_s: int = 600) -> dict:
    """What shock_scan.read_vix would make of the stored ^VIX tape row at `now`."""
    if not entry:
        return {"present": False, "proxy": None, "proxy_symbol": None, "has_level": False,
                "age_s": None, "fresh": False, "usable": False}
    as_of = _ts(entry.get("as_of"))
    age = None if as_of is None else (now - as_of).total_seconds()
    proxy, level = bool(entry.get("is_proxy")), entry.get("price") is not None
    fresh = age is not None and age <= max_age_s
    return {"present": True, "proxy": proxy, "proxy_symbol": entry.get("proxy_symbol"),
            "has_level": level, "age_s": age, "fresh": fresh,
            "usable": fresh and level and not proxy}


def coverage(rows: list[dict], max_age_s: int = 600) -> dict:
    """Null rates in the stored shadow rows (vix_chg_pct None = missing, proxy or stale)."""
    n = len(rows)
    vix_null = sum(r.get("vix_chg_pct") is None for r in rows)
    spy_null = sum(r.get("spy_atr_move") is None for r in rows)
    days = sorted({str(r["session_date"]) for r in rows})
    return {"rows": n, "sessions": len(days), "first": days[0] if days else None,
            "last": days[-1] if days else None, "max_age_s": max_age_s,
            "vix_null": vix_null, "vix_null_rate": _rate(vix_null, n),
            "spy_null": spy_null, "spy_null_rate": _rate(spy_null, n),
            "insufficient": sum(bool(r.get("insufficient")) for r in rows),
            "shock_rows": sum(r.get("state_after") == "SHOCK" for r in rows)}


def read_archive_1m(paths) -> pd.Series:
    """UTC bar start -> close from archive_vix.py's files (missing ones skipped)."""
    parts = [pd.read_csv(p, index_col=0)["Close"] for p in paths if Path(p).exists()]
    if not parts:
        return pd.Series(dtype=float)
    series = pd.concat(parts).astype(float)
    series.index = pd.to_datetime(series.index, utc=True)
    series = series.sort_index()
    return series[~series.index.duplicated(keep="last")]


def lag_points(rows: list[dict], vix_1m: pd.Series) -> list[dict]:
    """Tape VIX minus the real ^VIX close of the bar finished at the reading's minute."""
    out = []
    for r in rows:
        at = _ts(r.get("as_of"))
        if r.get("vix_level") is None or at is None:
            continue
        bar = pd.Timestamp(at).floor("min") - pd.Timedelta(minutes=1)
        if bar not in vix_1m.index:
            continue
        tape, real = float(r["vix_level"]), float(vix_1m.loc[bar])
        out.append({"as_of": at.isoformat(), "tape": tape, "index": real,
                    "lag_points": tape - real})
    return out


def _index_true(r: dict, k: float, v: float) -> bool:
    spy, vix = r.get("spy_atr_move"), r.get("vix_chg_pct")
    if k <= 0 or spy is None or vix is None:
        return False
    return -spy + EPS >= k and vix + EPS >= v


def _counts(r: dict, k: float, v: float) -> bool:
    m = r.get("minutes_since_open")
    return m is not None and m + EPS >= SETTLE_MIN and _index_true(r, k, v)


def _session_fires(rows: list[dict], k: float, v: float) -> bool:
    streak = 0
    for r in rows:
        if r.get("insufficient"):
            continue                       # shock.step holds the state
        streak = streak + 1 if _counts(r, k, v) else 0
        if streak >= 2:
            return True
    return False


def shadow_fire_rate(rows: list[dict], k: float, v: float) -> dict:
    """The index path alone on the stored rows (two consecutive settled readings)."""
    by_day: dict[str, list[dict]] = {}
    for r in sorted(rows, key=lambda r: str(r["as_of"])):
        by_day.setdefault(str(r["session_date"]), []).append(r)
    fired = [d for d, rs in sorted(by_day.items()) if _session_fires(rs, k, v)]
    true = sum(not r.get("insufficient") and _counts(r, k, v) for r in rows)
    return {"k": k, "v": v, "sessions": len(by_day), "readings_true": true,
            "sessions_fired": len(fired), "fired_days": fired,
            "rate": _rate(len(fired), len(by_day))}


def stage1_rate(stage1: dict, k: float, v: float) -> dict:
    cell = next(c for c in stage1["cells"] if (c["k"], c["v"]) == (k, v))
    sessions = int(stage1["window"]["sessions"])
    return {"upper_fires": cell["upper_fires"], "upper_episodes": cell["upper_episodes"],
            "sessions": sessions, "rate": _rate(cell["upper_fires"], sessions)}


def chunk_room(n_tickers: int, chunk_size: int, benchmark_in_watchlist: bool) -> dict:
    """shock_scan.quote_tickers appends the benchmark only into the last chunk's free room."""
    room = (-n_tickers) % max(1, int(chunk_size))
    return {"n_tickers": n_tickers, "room": room,
            "benchmark_in_watchlist": benchmark_in_watchlist,
            "benchmark_quoted": benchmark_in_watchlist or room >= 1}


def env_presence(counts: dict[str, int]) -> dict[str, bool]:
    return {key: int(counts.get(key, 0)) > 0 for key in ENV_KEYS}


def dump() -> dict:
    import sqlalchemy as sa

    import swingbot
    from swingbot import config
    from swingbot.core.db.engine import get_engine
    from swingbot.core.marketdata import watchlist
    from swingbot.core.marketdata.shared import tape
    entry = tape.read_tape([VIX_SYMBOL]).get(VIX_SYMBOL)
    with get_engine().connect() as conn:
        rows = [dict(row._mapping) for row in conn.execute(sa.text(COVERAGE_SQL))]
    archive = Path(swingbot.__file__).resolve().parents[1] / "market_data" / "vix" / "intraday_1m"
    days = sorted({str(r["session_date"]) for r in rows})
    vix_1m = read_archive_1m([archive / f"VIX_{d}_1m.csv" for d in days])
    tickers, bench = watchlist.load_watchlist(), str(config.MARKET_REGIME_TICKER)
    return {"now": datetime.now(timezone.utc).isoformat(), "rows": rows,
            "tape": None if entry is None else asdict(entry),
            "lag": lag_points(rows, vix_1m), "benchmark_is_spy": bench == "SPY",
            "chunk": chunk_room(len(tickers), int(config.BATCH_FETCH_CHUNK_SIZE),
                                bench in set(tickers))}


def build_report(dump_doc: dict, stage1: dict, k: float, v: float,
                 env_counts: dict[str, int]) -> dict:
    rows, lags = dump_doc["rows"], [p["lag_points"] for p in dump_doc["lag"]]
    lag = {"n": len(lags), "mean": sum(lags) / len(lags) if lags else None,
           "min": min(lags, default=None), "max": max(lags, default=None)}
    return {"now": dump_doc["now"], "tape": tape_status(dump_doc.get("tape"), _ts(dump_doc["now"])),
            "coverage": coverage(rows), "lag": lag, "chunk": dump_doc["chunk"],
            "benchmark_is_spy": dump_doc.get("benchmark_is_spy"),
            "env": env_presence(env_counts), "shadow": shadow_fire_rate(rows, k, v),
            "stage1": stage1_rate(stage1, k, v)}


def _tape_line(t: dict) -> str:
    if not t["present"] or t["proxy"]:
        what = f"proxy {t['proxy_symbol']}" if t["present"] else "missing"
        return f"**{what}**: `read_vix` gives no VIX, the index path can never fire"
    return f"non-proxy, level {t['has_level']}, age {t['age_s']:.0f} s, fresh {t['fresh']}"


def render_md(r: dict) -> str:
    c, lag, ch, s, s1 = r["coverage"], r["lag"], r["chunk"], r["shadow"], r["stage1"]
    lag_text = (f"{lag['n']} minutes, mean {lag['mean']:+.2f}, min {lag['min']:+.2f}, "
                f"max {lag['max']:+.2f}" if lag["n"] else "no archived one-minute `^VIX`")
    env = ", ".join(f"{k}: {'explicit' if on else 'absent'}" for k, on in r["env"].items())
    return "\n".join([
        f"- `^VIX` tape row at {r['now']}: {_tape_line(r['tape'])}.",
        f"- Shadow rows: {c['rows']} in {c['sessions']} sessions ({c['first']}..{c['last']}); "
        f"`vix_chg_pct` null {c['vix_null']} (missing, proxy or > {c['max_age_s']} s), "
        f"`spy_atr_move` null {c['spy_null']}, insufficient {c['insufficient']}, "
        f"SHOCK {c['shock_rows']}.",
        f"- Tape minus `^VIX` (VIX points): {lag_text}.",
        f"- SPY chunk room: {ch['n_tickers']} tickers, room {ch['room']}, benchmark listed "
        f"{ch['benchmark_in_watchlist']}, is SPY {r['benchmark_is_spy']}, "
        f"quoted {ch['benchmark_quoted']}.",
        f"- Explicit keys in production `.env` (match counts only): {env}.",
        f"- Frozen cell k = {s['k']}, v = {s['v']} on shadow rows: {s['readings_true']} readings "
        f"true, {s['sessions_fired']} of {s['sessions']} sessions fired; Stage 1 upper-bound "
        f"rate {s1['upper_fires']} of {s1['sessions']} sessions ({s1['upper_episodes']} episodes).",
    ]) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="v222 production check (read-only)")
    for flag in ("--dump-json", "--stage1-json", "--out-md"):
        p.add_argument(flag)
    p.add_argument("--k", type=float)
    p.add_argument("--v", type=float)
    p.add_argument("--env-count", action="append", default=[], metavar="KEY=N")
    args = p.parse_args(sys.argv[1:] if argv is None else argv)
    if not args.dump_json:
        print(json.dumps(dump(), default=str))
        return 0
    dump_doc = json.loads(Path(args.dump_json).read_text(encoding="utf-8"))
    stage1 = json.loads(Path(args.stage1_json).read_text(encoding="utf-8"))
    counts = {k: int(n) for k, _, n in (e.partition("=") for e in args.env_count)}
    md = render_md(build_report(dump_doc, stage1, args.k, args.v, counts))
    if args.out_md:
        Path(args.out_md).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

```bash
python "$W/scripts/dev/testrun.py" file tests/scripts/test_shock_vix_check.py
python "$W/scripts/dev/complexity_gate.py"
```

Expected: all pass; no function at or above 15.

- [ ] **Step 5: Commit**

```bash
git -C "$W" add scripts/reports/shock_vix_check.py tests/scripts/test_shock_vix_check.py
git -C "$W" commit -m "feat(v222): read-only production check for the index path (tape, nulls, lag, keys, shadow rate)"
```

- [ ] **Step 6: Run the check against production (read-only)**

Run it on a weekday in regular hours (14:30–21:00 UTC in winter) so the tape
row's age means something. Set `K` and `V` from the header snippet's output.

```bash
bash "$M/scripts/ops/ssh-hetzner.sh" "cd /opt/swing-bot && docker compose exec -T bot python -" \
  < "$W/scripts/reports/shock_vix_check.py" > "$D/prod_dump.json"
bash "$M/scripts/ops/ssh-hetzner.sh" "grep -c '^ *SHOCK_INDEX_ATR_K *=' /opt/swing-bot/.env; grep -c '^ *SHOCK_INDEX_VIX_CHG *=' /opt/swing-bot/.env; true" > "$D/prod_env_counts.txt"
A=$(sed -n 1p "$D/prod_env_counts.txt"); B=$(sed -n 2p "$D/prod_env_counts.txt")
python "$W/scripts/reports/shock_vix_check.py" --dump-json "$D/prod_dump.json" \
  --stage1-json "$D/stage1.json" --k "$K" --v "$V" --out-md "$D/prod_check.md" \
  --env-count "SHOCK_INDEX_ATR_K=$A" --env-count "SHOCK_INDEX_VIX_CHG=$B"
```

`grep -c` prints two counts, nothing of the file. Expected: six bullet lines.
A dump failure is not a result: fix or retry, never hand-write the section.
"No archived one-minute `^VIX`" is recorded as is.

- [ ] **Step 7: Write Results § Production check and commit on `main`**

```bash
python - "$SPEC" "$D/prod_check.md" <<'PYEOF'
import sys
from pathlib import Path
spec, body = Path(sys.argv[1]), Path(sys.argv[2]).read_text(encoding="utf-8")
doc = spec.read_text(encoding="utf-8")
marker = "### Production check\n\nPending V222-12.\n"
assert doc.count(marker) == 1, "Results § Production check is not pending"
spec.write_text(doc.replace(marker, "### Production check\n\n" + body), encoding="utf-8")
PYEOF
git -C "$M" add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C "$M" commit -m "docs(v222): results -- production check"
git -C "$M" status --short
```

Expected: one commit on `main`. A missing or proxy tape row, SPY not quoted,
or an `explicit` key is not fixed here: gate 3 (V222-13) puts it to the partner.

### Task V222-13: Stage 3 reports: 2026-11-05 in-sample and A1 days with ramp VIX, gate 3

**Model:** sonnet — two descriptive replays through the real `shock.step` with exact synthetic tests and one A1 parity check; nothing here gates, so the risk is a mislabelled report, pinned by the render test.

**Files:**
- Create: `scripts/backtest/shock_index_stage3.py`
- Create: `tests/backtest_scripts/test_shock_index_stage3.py` (suite `backtest-scripts`)
- Modify: `scripts/dev/select_tests.py` (append the new test to the vix1m row and the `tests/fixtures/shock_replay/` row)
- Modify (main tree, spec): `## Results` § Stage 3

**Interfaces:**
- Consumes: V222-9's `ShockThresholds(index_atr_k=..., index_vix_chg=...)` and `_index_path` inside `shock.step`; `shock.ShockState`, `shock.SHOCK`; from `scripts/backtest/shock_index_intraday.py` (V222-7, V222-7b): `readings(fx, th)`, `drop_ahead(rs, t, spy_daily)`, `a1_false_fire(fx, rs, first)`, `A1_RECORDED`; the test helpers `_fx`, `_lead_fx`, `at` of `tests/backtest_scripts/test_shock_index_intraday.py` (used as `base._fx`, never imported by name, so pytest does not collect that module's tests twice); `tests/fixtures/shock_replay_2026_11_05_vix1m.json` (V222-6d: `vix_interpolated: false`, `long_entries`); `tests/fixtures/shock_replay/` (`validation_days.json` `days{iso: {class, ...}}`, `<iso>.json.gz`), read only; Results § Production check (V222-12).
- Produces: `replay_labels(fx: dict, th: ShockThresholds) -> list[tuple[ShockReading, str]]`; `first_shock_at(out) -> datetime | None`; `in_sample_1105(fx: dict, k: float, v: float) -> dict` (`k, v, first_a1, first_idx, longs, before_a1, before_idx, steps`; raises `ValueError` unless `vix_interpolated is False`); `a1_ramp_report(a1_dir: Path, k: float, v: float, *, check_recorded: bool = True) -> dict` (`recall{a1, idx}`, `false_fires{calm|rotation|hard: {a1, idx}}`, `shock_days[]`; raises when A1 alone differs from its recorded row); `render_md(in_sample, ramp) -> str`; CLI `--fixture --a1-dir --k --v --out-md`; Results § Stage 3 and the gate 3 answer, which V222-14 reads.

Both reports are **descriptive**. 2026-11-05 is in-sample (its inputs were read
in the premise check); the A1 days' VIX is a ramp to the daily close. Neither
decides anything, neither is cited as support for the release, and gate 3
asks only whether to release.

- [ ] **Step 1: Write the failing tests**

Create `tests/backtest_scripts/test_shock_index_stage3.py`:

```python
"""v222 Stage 3: the in-sample 2026-11-05 report and the A1 days on ramp VIX."""
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "scripts" / "backtest") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts" / "backtest"))

import shock_index_stage3 as s3  # noqa: E402

import tests.backtest_scripts.test_shock_index_intraday as base  # noqa: E402


def _like_1105(fx: dict, interpolated=False) -> dict:
    fx = dict(fx, vix_interpolated=interpolated)
    fx.pop("session_date")                     # the 11-05 fixture has none
    fx["long_entries"] = [{"ticker": t, "opened_at": base.at(m).isoformat()}
                          for t, m in (("A", 20), ("B", 60), ("C", 130))]
    return fx


def test_the_index_path_moves_the_first_shock_and_the_longs_line():
    r = s3.in_sample_1105(_like_1105(base._lead_fx(vix=25.0)), 1.5, 20.0)
    assert (r["first_a1"], r["first_idx"]) == (base.at(120), base.at(30))
    assert (r["longs"], r["before_a1"], r["before_idx"]) == (3, 2, 1)
    assert len(r["steps"]) == 8 and r["steps"][1]["idx"] == "SHOCK"


def test_a_vix_change_below_the_cell_leaves_a1_alone():
    r = s3.in_sample_1105(_like_1105(base._lead_fx(vix=25.0)), 1.5, 30.0)
    assert r["first_idx"] == r["first_a1"] == base.at(120)


def test_the_interpolated_fixture_is_refused():
    with pytest.raises(ValueError, match="one-minute"):
        s3.in_sample_1105(_like_1105(base._lead_fx(), interpolated=True), 1.5, 20.0)


def test_the_committed_vix1m_fixture_replays_a1_at_its_recorded_time():
    fx = json.loads(s3.FIXTURE_1105.read_text(encoding="utf-8"))
    r = s3.in_sample_1105(fx, 1.5, 20.0)
    assert r["first_a1"] == datetime(2026, 11, 5, 15, 45, tzinfo=timezone.utc)
    assert len(r["steps"]) == 26


def _a1_dir(tmp_path: Path) -> Path:
    days = {"2025-07-15": ("shock", base._lead_fx(vix=25.0)),
            "2025-07-16": ("calm", base._fx([0] * 4, [-1.6] * 4, vix=25.0, close=500.0,
                                            day="2025-07-16")),
            "2025-07-17": ("calm", {"source": "unbuildable", "steps": []})}
    (tmp_path / "validation_days.json").write_text(json.dumps(
        {"days": {d: {"class": c} for d, (c, _) in days.items()}}), encoding="utf-8")
    for d, (_, fx) in days.items():
        (tmp_path / f"{d}.json.gz").write_bytes(gzip.compress(json.dumps(fx).encode()))
    return tmp_path


def test_the_ramp_report_scores_both_arms_like_a1(tmp_path):
    r = s3.a1_ramp_report(_a1_dir(tmp_path), 1.5, 20.0, check_recorded=False)
    assert r["recall"] == {"a1": 1, "idx": 1}
    assert r["false_fires"]["calm"] == {"a1": 1, "idx": 2}     # unbuildable counts for both
    assert r["false_fires"]["hard"] == {"a1": 0, "idx": 0}
    (day,) = r["shock_days"]
    assert (day["t_a1"], day["t_idx"]) == (base.at(120), base.at(30))
    assert day["ahead_idx"] == pytest.approx(22 / 30) and day["ahead_a1"] == pytest.approx(2 / 30)
    with pytest.raises(ValueError, match="recorded"):
        s3.a1_ramp_report(_a1_dir(tmp_path), 1.5, 20.0)


def test_a1_alone_on_the_frozen_days_matches_its_recorded_row():
    r = s3.a1_ramp_report(s3.A1_DIR, 1.5, 20.0)           # raises on any difference
    assert r["recall"]["a1"] == s3.A1_RECALL == 5


def test_the_markdown_labels_both_reports_descriptive(tmp_path):
    in_sample = s3.in_sample_1105(_like_1105(base._lead_fx(vix=25.0)), 1.5, 20.0)
    ramp = s3.a1_ramp_report(_a1_dir(tmp_path), 1.5, 20.0, check_recorded=False)
    md = s3.render_md(in_sample, ramp)
    assert "in-sample, decides nothing" in md and "uses the daily close" in md
    assert "A1 recorded" in md and "| 14:00 |" in md
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_stage3.py
```

Expected: FAIL at collection, `ModuleNotFoundError: No module named 'shock_index_stage3'`.

- [ ] **Step 3: Implement**

Create `scripts/backtest/shock_index_stage3.py`:

```python
#!/usr/bin/env python3
"""v222 Stage 3: two descriptive reports for the frozen cell. They decide nothing.

* 2026-11-05, in-sample: the fixture with real one-minute ^VIX, first SHOCK with
  and without the index path through the real shock.step, longs opened before each.
* The 26 A1 validation days on ramp VIX (the ramp uses the daily close): recall,
  false fires per class and drop still ahead, beside A1's recorded row.

    python scripts/backtest/shock_index_stage3.py --k K --v V --out-md data/v222/stage3.md
"""
from __future__ import annotations

import argparse
import gzip
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for _p in (ROOT, ROOT / "scripts" / "backtest"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import shock_index_intraday as sii  # noqa: E402

from swingbot.core.market import shock  # noqa: E402
from swingbot.core.market.shock import ShockThresholds  # noqa: E402

FIXTURE_1105 = ROOT / "tests" / "fixtures" / "shock_replay_2026_11_05_vix1m.json"
A1_DIR = ROOT / "tests" / "fixtures" / "shock_replay"
A1_RECALL = 5                                  # A1's recorded hits of 6 shock days
NEG = ("calm", "rotation", "hard")
ARMS = ("a1", "idx")


def replay_labels(fx: dict, th: ShockThresholds) -> list[tuple[shock.ShockReading, str]]:
    """Every reading with the label the real detector gives it."""
    state, out = shock.ShockState(), []
    for r in sii.readings(fx, th):
        state = shock.step(state, r, th)
        out.append((r, state.label))
    return out


def first_shock_at(out) -> datetime | None:
    return next((r.as_of for r, label in out if label == shock.SHOCK), None)


def _cell(k: float, v: float) -> ShockThresholds:
    return ShockThresholds(index_atr_k=k, index_vix_chg=v)


def _before(entries: list[dict], first: datetime | None) -> int:
    if first is None:
        return len(entries)
    return sum(datetime.fromisoformat(e["opened_at"]) < first for e in entries)


def in_sample_1105(fx: dict, k: float, v: float) -> dict:
    if fx.get("vix_interpolated") is not False:
        raise ValueError("Stage 3 reads the real one-minute ^VIX fixture, not the interpolated one")
    a1, idx = replay_labels(fx, ShockThresholds()), replay_labels(fx, _cell(k, v))
    t_a1, t_idx = first_shock_at(a1), first_shock_at(idx)
    entries = fx.get("long_entries", [])
    steps = [{"as_of": r.as_of, "spy_atr_move": r.spy_atr_move, "vix_chg_pct": r.vix_chg_pct,
              "a1": la, "idx": li} for (r, la), (_, li) in zip(a1, idx)]
    return {"k": k, "v": v, "first_a1": t_a1, "first_idx": t_idx, "longs": len(entries),
            "before_a1": _before(entries, t_a1), "before_idx": _before(entries, t_idx),
            "steps": steps}


def _load(a1_dir: Path) -> dict[str, tuple[str, dict]]:
    days = json.loads((a1_dir / "validation_days.json").read_text(encoding="utf-8"))["days"]
    return {d: (info["class"], json.loads(gzip.decompress((a1_dir / f"{d}.json.gz").read_bytes())))
            for d, info in sorted(days.items())}


def _ahead(rs, t, spy) -> float | None:
    return None if t is None or not rs else sii.drop_ahead(rs, t, spy)


def _day(fx: dict, k: float, v: float) -> dict:
    rs = sii.readings(fx)
    t_a1 = first_shock_at(replay_labels(fx, ShockThresholds()))
    t_idx = first_shock_at(replay_labels(fx, _cell(k, v)))
    spy = fx.get("spy_daily")
    return {"bad": sii.a1_false_fire(fx, rs, None), "t_a1": t_a1, "t_idx": t_idx,
            "ahead_a1": _ahead(rs, t_a1, spy), "ahead_idx": _ahead(rs, t_idx, spy)}


def _count(rows, cls: str, arm: str, hit: bool) -> int:
    """A1's rules: a hit is clean and fired; a false fire is bad or fired."""
    if hit:
        return sum(c == cls and not r["bad"] and r[f"t_{arm}"] is not None for c, r in rows)
    return sum(c == cls and (r["bad"] or r[f"t_{arm}"] is not None) for c, r in rows)


def a1_ramp_report(a1_dir: Path, k: float, v: float, *, check_recorded: bool = True) -> dict:
    days = {d: (cls, _day(fx, k, v)) for d, (cls, fx) in _load(Path(a1_dir)).items()}
    rows = list(days.values())
    recall = {arm: _count(rows, "shock", arm, True) for arm in ARMS}
    false = {cls: {arm: _count(rows, cls, arm, False) for arm in ARMS} for cls in NEG}
    a1_row = {cls: false[cls]["a1"] for cls in NEG}
    if check_recorded and (recall["a1"], a1_row) != (A1_RECALL, sii.A1_RECORDED):
        raise ValueError(f"A1 alone {recall['a1']}/{a1_row} differs from its recorded row")
    shock_days = [{"day": d, **{key: r[key] for key in ("t_a1", "t_idx", "ahead_a1", "ahead_idx")}}
                  for d, (cls, r) in days.items() if cls == "shock"]
    return {"k": k, "v": v, "recall": recall, "false_fires": false, "shock_days": shock_days}


def _hm(t: datetime | None) -> str:
    return "never" if t is None else t.strftime("%H:%M")


def _share(x: float | None) -> str:
    return "–" if x is None else f"{100 * x:.0f} %"


def _num(x: float | None) -> str:
    return "–" if x is None else f"{x:+.2f}"


def render_md(ins: dict, ramp: dict) -> str:
    lines = [f"**2026-11-05 (in-sample, decides nothing)**, k = {ins['k']}, v = {ins['v']}, "
             "real one-minute `^VIX`: first SHOCK "
             f"A1 {_hm(ins['first_a1'])} UTC, A1 + index {_hm(ins['first_idx'])} UTC; "
             f"of {ins['longs']} longs opened at/after 14:36 UTC, {ins['before_a1']} came "
             f"before A1's SHOCK and {ins['before_idx']} before A1 + index.", "",
             "| UTC | SPY ATR move | VIX chg % | A1 | A1 + index |", "|---|---|---|---|---|"]
    lines += [f"| {_hm(s['as_of'])} | {_num(s['spy_atr_move'])} | {_num(s['vix_chg_pct'])} | "
              f"{s['a1']} | {s['idx']} |" for s in ins["steps"]]
    rec, ff = ramp["recall"], ramp["false_fires"]
    lines += ["", "**A1 validation days, ramp VIX (descriptive only: the ramp uses the daily "
              "close).** A1 recorded: recall 5/6, false fires calm 0/12, rotation 1/4, hard 0/4.",
              f"A1 + index: recall {rec['idx']}/6 (A1 here {rec['a1']}/6); false fires "
              + ", ".join(f"{c} {ff[c]['idx']} (A1 {ff[c]['a1']})" for c in NEG) + ".", "",
              "| Shock day | A1 first SHOCK | ahead | A1 + index | ahead |", "|---|---|---|---|---|"]
    lines += [f"| {d['day']} | {_hm(d['t_a1'])} | {_share(d['ahead_a1'])} | {_hm(d['t_idx'])} | "
              f"{_share(d['ahead_idx'])} |" for d in ramp["shock_days"]]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="v222 Stage 3 reports (descriptive)")
    p.add_argument("--fixture", default=str(FIXTURE_1105))
    p.add_argument("--a1-dir", default=str(A1_DIR))
    p.add_argument("--k", type=float, required=True)
    p.add_argument("--v", type=float, required=True)
    p.add_argument("--out-md")
    args = p.parse_args(argv)
    fx = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    md = render_md(in_sample_1105(fx, args.k, args.v), a1_ramp_report(Path(args.a1_dir), args.k, args.v))
    if args.out_md:
        Path(args.out_md).write_text(md, encoding="utf-8")
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Route the two fixtures to the new test**

In `scripts/dev/select_tests.py`, append the new test to the vix1m row (V222-6d)
and to the `tests/fixtures/shock_replay/` row (V222-7):

```python
    ("tests/fixtures/shock_replay/", ("tests/market/test_shock_acceptance_a1.py",
                                      "tests/backtest_scripts/test_shock_index_intraday.py",
                                      "tests/backtest_scripts/test_shock_index_stage3.py")),
```

```python
    ("tests/fixtures/shock_replay_2026_11_05_vix1m.json",
     ("tests/scripts/test_build_shock_replay_fixture.py",
      "tests/backtest_scripts/test_shock_index_stage3.py")),
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
python "$W/scripts/dev/testrun.py" file tests/backtest_scripts/test_shock_index_stage3.py
python "$W/scripts/dev/testrun.py" file tests/dev/test_select_tests.py
python "$W/scripts/dev/complexity_gate.py"
```

Expected: all pass. `test_a1_alone_on_the_frozen_days_matches_its_recorded_row`
failing means this replay differs from A1's run: stop and report, never edit
the fixtures, the A1 test or `A1_RECALL`.

- [ ] **Step 6: Commit**

```bash
git -C "$W" add scripts/backtest/shock_index_stage3.py tests/backtest_scripts/test_shock_index_stage3.py
git -C "$W" commit -m "feat(v222): Stage 3 reports -- 2026-11-05 in-sample and A1 days on ramp VIX (descriptive)"
git -C "$W" add scripts/dev/select_tests.py
git -C "$W" commit -m "chore(v222): route the vix1m and A1 fixtures to the Stage 3 test"
```

- [ ] **Step 7: Run the reports once and write Results § Stage 3 on `main`**

Set `K` and `V` from the header snippet's output. Run once; the output is
reported as is, never re-run with another cell.

```bash
python "$W/scripts/backtest/shock_index_stage3.py" --k "$K" --v "$V" --out-md "$D/stage3.md"
python - "$SPEC" "$D/stage3.md" <<'PYEOF'
import sys
from pathlib import Path
spec, body = Path(sys.argv[1]), Path(sys.argv[2]).read_text(encoding="utf-8")
doc = spec.read_text(encoding="utf-8")
marker = "### Stage 3\n\nPending V222-13.\n"
assert doc.count(marker) == 1, "Results § Stage 3 is not pending"
spec.write_text(doc.replace(marker, "### Stage 3\n\n" + body), encoding="utf-8")
PYEOF
wc -l "$SPEC"
git -C "$M" add docs/superpowers/specs/2026-11-09-v222-shock-index-vix-path-design.md
git -C "$M" commit -m "docs(v222): results -- Stage 3 (descriptive)"
```

Expected: the spec stays under 1500 lines (at 1500 or more, move the 26-row
11-05 step table to `data/v222/stage3.md` and leave a pointer).

- [ ] **Step 8: Gate 3 (partner, `AskUserQuestion`, one question per message, recommended option first)**

Read Results § Production check and § Stage 3. Ask the questions that apply,
one per message, in this order; a **Hold** answer stops the plan before V222-14
(it stays open; nothing is closed `no-lift/`):

1. Only if the tape row is missing or a proxy, or SPY is not quoted: "Production
   cannot fire the index path today (<the Results line>). Release the frozen
   cell anyway as a shadow default that stays silent until that is fixed?"
   Options: **"Release; Results records it cannot fire yet (Recommended)"**;
   **"Hold the release"**.
2. Only if a `SHOCK_INDEX_*` key is `explicit`: "Production's `.env` sets
   <key(s)> explicitly, which overrides the new default. Release, and at deploy
   edit the key(s) in place to the frozen cell under `mirror-prod`?" Options:
   **"Release with the in-place edit at deploy (Recommended)"**; **"Hold the release"**.
3. Always: "Release k = <K>, v = <V> as the config default (V222-14)? The
   production check is in Results; the Stage 3 reports are descriptive and
   decide nothing." Options: **"Release as the config default (Recommended)"**;
   **"Hold the release"**.

No option re-runs a stage, changes the cell or treats Stage 3 as evidence.
Append under Results § Stage 3 `Gate 3 (<date>): <answers>.` and commit on
`main` (`docs(v222): results -- gate 3`). Release: go on to V222-14.

```bash
git -C "$M" status --short
```

Expected: nothing of v222 beyond plan files the controller has open.

### Task V222-14: Release: frozen cell becomes the config `Field` default

**Model:** sonnet — mechanical default changes along V222-10's pins plus a version bump; the traps (the A1 record, an explicit production key, the regenerated version matrix) are each pinned by a test or a command here.

**Files:**
- Modify: `swingbot/config.py` (the two `SHOCK_INDEX_*` `Field`s from V222-10: `default`, `help`)
- Modify: `.env.example` (the v222 index-path lines from V222-10)
- Modify: `tests/test_config_v209_keys.py` (`V209_FIELDS`, `CAST_DEFAULTS`, `FROZEN_K`/`FROZEN_V`, the reworded default test, the env test's last line, one new override test)
- Modify: `tests/scanning/test_shock_scan.py` (one new test)
- Modify: `docs/deploy/DEPLOY_HETZNER.md` (a v222 paragraph after the v210 one: release check and rollback lever)
- Modify: `VERSION.json`, `swingbot/admin/version_history.json` (bot patch, two commits)

**Interfaces:**
- Consumes: gate 3 = release (Results § Stage 3); the frozen cell (header snippet); Results § Production check (explicit-key presence); V222-10's `Field`s, `.env.example` lines and pins (`V222_KEYS`, `_field`, `test_index_keys_are_off_at_zero_with_a_zero_floor`, `test_an_env_index_key_reaches_the_detector_thresholds`); `$W/logs/v222/a1_report_before.txt` (V222-9's A1 report before any v222 change); `scripts/ops/env_set.py` (in-place `.env` edit on the VM); `scripts/dev/build_version_matrix.py`.
- Produces: `config.SHOCK_INDEX_ATR_K` / `SHOCK_INDEX_VIX_CHG` defaults = `FROZEN_K` / `FROZEN_V` (strings `str(float(k))`, e.g. `"1.5"`, `"20.0"`), help stating the VIX half was never tested intraday on a shock day; `ShockThresholds()` stays `0.0` (pinned); the bot patch release.

What stays as it is: `ShockThresholds` (dataclass defaults `0.0`), the A1
test and its fixtures, `test_a_missing_index_attr_falls_back_to_off` (a
missing config attr still falls back to the dataclass's `0.0`), and
`SHOCK_VIX_SPIKE_PCT`'s help: "VIX never triggers SHOCK on its own" is still
true, because the index path needs SPY one or more ATR down as well.

- [ ] **Step 1: Write the failing tests**

Save as `$W/logs/v222/release_tests.py` (scratch under the worktree's
gitignored `logs/`, never committed) and run it with
`python "$W/logs/v222/release_tests.py" "$SPEC" "$W"`. It edits the two test
files exactly; every anchor must match once, or it stops and nothing is written.

```python
"""v222 V222-14: point the config pins at the frozen cell (exact edits, all or none)."""
import re
import sys
from pathlib import Path

spec, w = Path(sys.argv[1]), Path(sys.argv[2])
m = re.search(r"\*\*Frozen cell: FROZEN_K = ([0-9.]+), FROZEN_V = ([0-9.]+)\.\*\*",
              spec.read_text(encoding="utf-8"))
k, v = float(m.group(1)), float(m.group(2))
K, V = str(k), str(v)                                    # Field default strings
NEW_DEFAULT_TEST = f'''# v222 release (V222-14): the Results § Stage 2 frozen cell.
FROZEN_K, FROZEN_V = {k!r}, {v!r}


@pytest.mark.parametrize("attr, frozen", list(zip(V222_KEYS, (FROZEN_K, FROZEN_V))))
def test_index_keys_default_to_the_frozen_cell_with_a_zero_floor(attr, frozen):
    field = _field(attr)
    assert "v222" in field.help and "v209" in field.help
    assert "never tested intraday on a shock day" in field.help
    assert field.min == 0
    value = config._cast(field, field.default)
    assert value == frozen and type(value) is float
    assert config._cast(field, "0") == 0.0          # the rollback lever still casts


def test_an_explicit_zero_in_env_overrides_the_released_default(monkeypatch):
    """The release check and the rollback lever: an explicit key beats the default."""
    from swingbot.core.scanning import shock_scan
    monkeypatch.setenv("SHOCK_INDEX_ATR_K", "0")
    try:
        config._apply_env()
        assert shock_scan.thresholds_from_config().index_atr_k == 0.0
    finally:
        monkeypatch.undo()
        config._apply_env()
    assert shock_scan.thresholds_from_config().index_atr_k == FROZEN_K
'''
SCAN_TEST = '''

def test_the_released_default_reaches_the_thresholds_but_the_dataclass_stays_off(monkeypatch):
    by_attr = {f.attr: f for f in config.FIELDS}
    k, v = (config._cast(by_attr[a], by_attr[a].default)
            for a in ("SHOCK_INDEX_ATR_K", "SHOCK_INDEX_VIX_CHG"))
    assert k > 0 and v > 0                               # v222 released: the path is on
    monkeypatch.setattr(config, "SHOCK_INDEX_ATR_K", k)
    monkeypatch.setattr(config, "SHOCK_INDEX_VIX_CHG", v)
    th = shock_scan.thresholds_from_config()
    assert (th.index_atr_k, th.index_vix_chg) == (k, v)
    off = shock.ShockThresholds()                        # A1's closed record replays this
    assert (off.index_atr_k, off.index_vix_chg) == (0.0, 0.0)
'''
cfg = w / "tests/test_config_v209_keys.py"
text = cfg.read_text(encoding="utf-8")
edits = [
    ('"SHOCK_INDEX_ATR_K": ("float", "0.0"),', f'"SHOCK_INDEX_ATR_K": ("float", "{K}"),'),
    ('"SHOCK_INDEX_VIX_CHG": ("float", "0.0"),', f'"SHOCK_INDEX_VIX_CHG": ("float", "{V}"),'),
    ('"SHOCK_INDEX_ATR_K": 0.0, "SHOCK_INDEX_VIX_CHG": 0.0,',
     f'"SHOCK_INDEX_ATR_K": {k!r}, "SHOCK_INDEX_VIX_CHG": {v!r},'),
    ("    assert shock_scan.thresholds_from_config().index_atr_k == 0.0\n",
     "    assert shock_scan.thresholds_from_config().index_atr_k == FROZEN_K\n"),
]
for old, new in edits:                                  # before the new tests go in
    assert text.count(old) == 1, f"anchor not found once: {old}"
    text = text.replace(old, new)
start = text.index("@pytest.mark.parametrize(\"attr\", V222_KEYS)\n"
                   "def test_index_keys_are_off_at_zero_with_a_zero_floor")
end = text.index("\n\n\ndef ", start) + 3
text = text[:start] + NEW_DEFAULT_TEST + "\n\n" + text[end:]
scan = w / "tests/scanning/test_shock_scan.py"
cfg.write_text(text, encoding="utf-8")
scan.write_text(scan.read_text(encoding="utf-8").rstrip("\n") + "\n" + SCAN_TEST,
                encoding="utf-8")
print(f"pins -> FROZEN_K={k}, FROZEN_V={v}")
```

The edits run before the new tests are spliced in, so the env test's old last
line (`... index_atr_k == 0.0`, four-space indent) is matched once; `FROZEN_*`
sit above every test that uses them.

- [ ] **Step 2: Run the tests to verify they fail**

```bash
python "$W/scripts/dev/testrun.py" file tests/test_config_v209_keys.py
python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_scan.py
```

Expected: FAIL — the per-field default, default-cast and `.env.example` line
tests for both keys, the reworded default
test (`never tested intraday` missing, `0.0 != FROZEN_K`), the env and
override tests' last lines, and the new scan test (`k > 0`).

- [ ] **Step 3: Implement**

Save as `$W/logs/v222/release_impl.py`, run with
`python "$W/logs/v222/release_impl.py" "$SPEC" "$W"` (same all-or-none rule):

```python
"""v222 V222-14: the frozen cell becomes the config Field default (exact edits)."""
import re
import sys
from pathlib import Path

spec, w = Path(sys.argv[1]), Path(sys.argv[2])
m = re.search(r"\*\*Frozen cell: FROZEN_K = ([0-9.]+), FROZEN_V = ([0-9.]+)\.\*\*",
              spec.read_text(encoding="utf-8"))
K, V = str(float(m.group(1))), str(float(m.group(2)))
NOTE = ("The default is the v222 frozen cell; its VIX half was never tested intraday on "
        "a shock day (Stage 2 forced it true), so production's shadow rows are its first test.")
EDITS = {
    "swingbot/config.py": [
        ('"Index path: SPY down-move, in ATR14 (0 = off)",\n          type="float", default="0.0",',
         f'"Index path: SPY down-move, in ATR14 (0 = off)",\n          type="float", default="{K}",'),
        ('"Index path: VIX day change (%)",\n          type="float", default="0.0",',
         f'"Index path: VIX day change (%)",\n          type="float", default="{V}",'),
        ('"never fires it. VIX relief does not apply to it."),',
         f'"never fires it. VIX relief does not apply to it. {NOTE} Rollback: 0."),'),
        ('"beside SHOCK_INDEX_ATR_K. Inert while SHOCK_INDEX_ATR_K is 0."),',
         f'"beside SHOCK_INDEX_ATR_K. Inert while SHOCK_INDEX_ATR_K is 0. {NOTE}"),'),
    ],
    ".env.example": [
        ("# its prior close and ^VIX is up SHOCK_INDEX_VIX_CHG % on the day. 0.0 = off.\n"
         "SHOCK_INDEX_ATR_K=0.0\nSHOCK_INDEX_VIX_CHG=0.0\n",
         "# its prior close and ^VIX is up SHOCK_INDEX_VIX_CHG % on the day. 0 = off.\n"
         "# Defaults = the v222 frozen cell. The VIX half was never tested intraday on a\n"
         "# shock day (Stage 2 forced it true): production's shadow rows are its first test.\n"
         f"SHOCK_INDEX_ATR_K={K}\nSHOCK_INDEX_VIX_CHG={V}\n"),
    ],
}
out = {}
for rel, pairs in EDITS.items():
    text = (w / rel).read_text(encoding="utf-8")
    for old, new in pairs:
        assert text.count(old) == 1, f"{rel}: anchor not found once: {old[:60]}"
        text = text.replace(old, new)
    out[rel] = text
for rel, text in out.items():
    (w / rel).write_text(text, encoding="utf-8")
print(f"defaults -> SHOCK_INDEX_ATR_K={K}, SHOCK_INDEX_VIX_CHG={V}")
```

The help strings are adjacent string literals in V222-10's `Field`s, so the
appended sentence joins the existing text. Then, in `docs/deploy/DEPLOY_HETZNER.md`,
directly after the v210 paragraph (it ends "ask before deleting those rows.")
and before `## Accessing the admin UI`, add (with the frozen values written in):

```markdown
**v222: market-shock index path, on by default (shadow).** No revision, no new
table, no stored field. `SHOCK_INDEX_ATR_K` / `SHOCK_INDEX_VIX_CHG` default to
the frozen cell `<K>` / `<V>`: a fourth NORMAL -> SHOCK entry path (SPY at least
`<K>` ATR14 down and `^VIX` up at least `<V>` %) that shares the two-reading
streak. The label still never blocks a trade. Its VIX half was never tested
intraday on a shock day; the shadow rows are its first test.

- **Release check (before the deploy):** `grep -c '^ *SHOCK_INDEX_' /opt/swing-bot/.env`
  prints `0`. An explicit key overrides the new default (a copied `0.0` keeps
  the path off): set it in place to the frozen cell with
  `python3 scripts/ops/env_set.py SHOCK_INDEX_ATR_K <K>` (and `SHOCK_INDEX_VIX_CHG <V>`)
  under `mirror-prod`, never `sed -i`.
- **Rollback lever:** `python3 scripts/ops/env_set.py SHOCK_INDEX_ATR_K 0`, then
  `docker compose kill -s SIGHUP bot`; mirror it back per `mirror-prod`. The
  depth, majority and fast paths are untouched by it.
```

- [ ] **Step 4: Run the tests to verify they pass, and the A1 record**

```bash
python "$W/scripts/dev/testrun.py" file tests/test_config_v209_keys.py
python "$W/scripts/dev/testrun.py" file tests/scanning/test_shock_scan.py
for t in test_shock_pass test_shock_pass_notice test_shock_step_gate test_shock_plans_byte_identical test_shock_index_path; do
  python "$W/scripts/dev/testrun.py" file "tests/scanning/$t.py"; done
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_step_entry.py
python "$W/scripts/dev/testrun.py" file tests/market/test_shock_acceptance_a1.py
python - "$W/.pytest-last-run.log" "$W/logs/v222/a1_report_release.txt" <<'PY'
import sys
lines = open(sys.argv[1], encoding="utf-8").read().splitlines()
start = next(i for i, l in enumerate(lines) if l.strip() == "v209 A1 acceptance (one shot)")
end = next(i for i in range(start, len(lines)) if lines[i].startswith("verdict:"))
open(sys.argv[2], "w", encoding="utf-8").write("\n".join(lines[start:end + 1]) + "\n")
print(lines[end])
PY
diff "$W/logs/v222/a1_report_before.txt" "$W/logs/v222/a1_report_release.txt" && echo SAME-REPORT
git -C "$W" diff --quiet main -- tests/market/test_shock_acceptance_a1.py tests/fixtures/shock_replay tests/fixtures/shock_replay_2026_11_05.json && echo A1-UNTOUCHED
python "$W/scripts/dev/complexity_gate.py"
```

Expected: all pass; `verdict: PASS`, `SAME-REPORT`, `A1-UNTOUCHED`. A scanning
test that now fails because its fixture meets the released index path was
written for the A1-only default: pin `monkeypatch.setattr(config,
"SHOCK_INDEX_ATR_K", 0.0)` in that test with a `# v222: A1-only scenario`
comment, never change its assertions, and name it in the commit body. A
`SAME-REPORT` diff is a stop: the A1 test reads `ShockThresholds()`, which
this task must not touch.

- [ ] **Step 5: Commit the release in scoped commits**

```bash
git -C "$W" add swingbot/config.py .env.example
git -C "$W" commit -m "feat(v222): the frozen index-path cell becomes the SHOCK_INDEX_* default (shadow)" \
  -m "The VIX half was never tested intraday on a shock day (Stage 2 forced it true); production's shadow rows are its first test. ShockThresholds() stays 0.0, so the A1 record is unchanged."
git -C "$W" add tests/test_config_v209_keys.py tests/scanning/test_shock_scan.py
git -C "$W" commit -m "test(v222): pins follow the released default; explicit env key overrides it; dataclass stays off"
git -C "$W" add docs/deploy/DEPLOY_HETZNER.md
git -C "$W" commit -m "docs(v222): deploy note -- release check and SHOCK_INDEX_ATR_K=0 rollback lever"
```

If Step 4 pinned an A1-only scanning test, add it to the test commit.

- [ ] **Step 6: Bump bot patch (two commits: bump, then regenerate)**

Read `VERSION.json` in the worktree; the new `bot` is the current one with its
patch part plus one (integers, e.g. `2.18.6` -> `2.18.7`), `bot_updated` the
UTC time as `YYYY-MM-DD HH-MM-SS`; `ui` and `ui_updated` stay.

```bash
python - "$W/VERSION.json" <<'PY'
import json, sys
from datetime import datetime, timezone
path = sys.argv[1]
doc = json.load(open(path, encoding="utf-8"))
major, minor, patch = (int(x) for x in doc["bot"].split("."))
doc["bot"] = f"{major}.{minor}.{patch + 1}"
doc["bot_updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H-%M-%S")
open(path, "w", encoding="utf-8").write(json.dumps(doc, indent=2) + "\n")
print(doc["bot"])
PY
git -C "$W" diff VERSION.json
git -C "$W" add VERSION.json
git -C "$W" commit -m "release(bot): <new bot version> -- market-shock index path on by default in shadow (v222)" \
  -m "SHOCK_INDEX_ATR_K / SHOCK_INDEX_VIX_CHG default to the frozen cell. The VIX half was never tested intraday on a shock day (Stage 2 forced it true); production's shadow rows are its first test. Rollback: SHOCK_INDEX_ATR_K=0 in place + SIGHUP (docs/deploy/DEPLOY_HETZNER.md)."
python "$W/scripts/dev/build_version_matrix.py"
python "$W/scripts/dev/testrun.py" file tests/scripts/test_build_version_matrix.py
git -C "$W" add swingbot/admin/version_history.json
git -C "$W" commit -m "chore(bot): <new bot version> -- market-shock index path on by default in shadow (v222)"
git -C "$M" status --short
```

Write the printed version into both messages. Expected:
`test_build_version_matrix.py` passes (the regenerated file's `current` pair
equals `VERSION.json`); the diff touches only `bot` and `bot_updated`; the
main tree shows nothing of this task. No merge and no deploy here: the
controller merges, CI runs the full suite, and the deploy runs the release
check above first.

