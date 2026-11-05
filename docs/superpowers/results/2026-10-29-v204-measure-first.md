# v204 measure-first: Analytics and Calendar under persisted FX alone

**Plan:** v204 task V204-2. **Rule:** `request` when warm max ≤ 0.5 s and cold max ≤ 1.0 s over 5 runs each; else `snapshot`.
**Run:** 2026-11-05T10:09:58+00:00, commit 2f1e92f0, replica restored 2026-11-05 UTC, alembic v200_001, `ADMIN_REFRESHER=on`, network poisoned (no call recorded).
**Book:** 1127 trades (1111 closed), 86 persisted quote currencies.

| route | warm runs (s) | warm max | cold runs (s) | cold max | verdict |
| --- | --- | ---: | --- | ---: | --- |
| `analytics.performance` | 6.592, 5.697, 5.783, 5.317, 5.652 | 6.592 | 8.254, 9.282, 8.093, 8.793, 6.354 | 9.282 | snapshot |
| `analytics.equity_curve` | 1.363, 1.421, 1.589, 1.450, 1.764 | 1.764 | 2.817, 3.026, 2.955, 2.927, 2.409 | 3.026 | snapshot |
| `calendar.pnl` | 1.078, 1.071, 0.898, 0.853, 1.057 | 1.078 | 1.996, 1.996, 2.940, 1.843, 2.021 | 2.940 | snapshot |

- `analytics.performance`: **snapshot** (warm max 6.592 s, cold max 9.282 s)
- `analytics.equity_curve`: **snapshot** (warm max 1.764 s, cold max 3.026 s)
- `calendar.pnl`: **snapshot** (warm max 1.078 s, cold max 2.940 s)
