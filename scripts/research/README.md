# scripts/research/

One-off research scripts that **describe the market** rather than test a
strategy. Nothing here is a backtest, a screen or a gate: a figure from these
scripts never licenses a live change (`docs/claude/backtest-methodology.md`).

Rules for every script in this folder:

- A fixed end date in the script, never "today", so a rerun reproduces the
  committed results doc.
- Inputs come from a hash-pinned cache; the script refuses to run when a
  file's SHA-256 differs from the recorded value.
- Any run past a few minutes checkpoints each finished unit to disk and a
  restart skips it (CLAUDE.md § Long runs).
- Results go to `docs/superpowers/results/` as Markdown written with
  `encoding="utf-8", newline="\n"`, carrying the command, the end date and
  the input hashes.

| Script | Plan | Cache | Results |
|---|---|---|---|
| `regime_base_rates.py` (SPY base rates under the v239 bear-regime rules, 1993 → 2026-11-20; DESCRIPTION, moves no gate) | v244 | `data/backtest_cache_regime/` (`scripts/data/fetch_regime_data.py`) | `docs/superpowers/results/2026-11-23-v244-regime-base-rates.md` |
