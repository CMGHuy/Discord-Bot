# v204 measure-first: Analytics and Calendar under persisted FX alone

**Plan:** v204 task V204-2. **Rule:** `request` when warm max ≤ 0.5 s and cold max ≤ 1.0 s over 5 runs each; else `snapshot`.
**Run:** 2026-11-05T09:50:35+00:00, commit 222346c7, replica restored 2026-11-05 UTC, alembic v200_001, `ADMIN_REFRESHER=on`, network poisoned (no call recorded).
**Book:** 1127 trades (1111 closed), 86 persisted quote currencies.

| route | warm runs (s) | warm max | cold runs (s) | cold max | verdict |
| --- | --- | ---: | --- | ---: | --- |
| `analytics.performance` | 3.011, 3.000, 3.606, 3.143, 3.123 | 3.606 | 3.257, 4.423, 5.039, 9.870, 9.215 | 9.870 | snapshot |
| `analytics.equity_curve` | 1.734, 1.900, 1.693, 2.602, 3.213 | 3.213 | 3.917, 1.498, 2.946, 3.390, 2.329 | 3.917 | snapshot |
| `calendar.pnl` | 1.089, 0.829, 0.750, 0.751, 0.662 | 1.089 | 2.857, 2.852, 3.147, 2.717, 2.171 | 3.147 | snapshot |

- `analytics.performance`: **snapshot** (warm max 3.606 s, cold max 9.870 s)
- `analytics.equity_curve`: **snapshot** (warm max 3.213 s, cold max 3.917 s)
- `calendar.pnl`: **snapshot** (warm max 1.089 s, cold max 3.147 s)
