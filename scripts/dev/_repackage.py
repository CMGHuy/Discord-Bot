#!/usr/bin/env python3
"""One-shot helper for the v26 core re-package. Deleted by Task 15 of plan v27.

Moves one sub-package's modules under swingbot/core/<pkg>/ and rewrites every
reference to them across the repo.

    python scripts/dev/_repackage.py infra

Rewrites five distinct forms:
  1. from swingbot.core.MOD import X   -> from swingbot.core.PKG.MOD import X
  2. import swingbot.core.MOD [as A]   -> import swingbot.core.PKG.MOD [as A]
  3. "swingbot.core.MOD..." strings    -> "swingbot.core.PKG.MOD..."
  4. from swingbot.core import MOD     -> from swingbot.core.PKG import MOD
  5. from .MOD / from ..MOD relatives  -> absolute swingbot.core.PKG.MOD
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# The COMPLETE final map. Every move needs the whole map, not just its own
# package: a module being moved may relatively-import a sibling that has not
# moved yet, and that import must be rewritten to the sibling's FINAL home.
_LAYOUT = {
    "marketdata": "data data_store data_refresh backtest_cache fmp_client "
                  "export_data ticker_directory ticker_utils universe watchlist",
    "market": "indicators candlestick_patterns fvg levels levels_lifecycle "
              "trendlines volatility market_context signals strategy "
              "strategy_types entry_filters reversal explain events market_events",
    "planning": "plan_engine plan_manager plan_store quality account",
    "backtesting": "backtest backtest_wf backtest_scenarios registry shadow_log",
    "tracking": "performance retrospective risk_metrics",
    "infra": "jsonio state notifier silent_channel",
}
MAP = {m: pkg for pkg, mods in _LAYOUT.items() for m in mods.split()}

SEARCH_ROOTS = ["swingbot", "tests", "scripts", "bot.py", "admin_ui.py"]


def source_files() -> list[Path]:
    out = subprocess.run(["git", "ls-files", *SEARCH_ROOTS],
                         cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / p for p in out.stdout.split() if p.endswith(".py")]


def rewrite(text: str) -> str:
    """Apply all five forms. Idempotent: re-running changes nothing."""

    # Forms 1-3: any dotted swingbot.core.MOD reference, in code or in a string.
    # MAP lookup means already-moved modules and never-moving packages
    # (charts, edge, scanning, analytics) are left alone.
    def _dotted(m: re.Match) -> str:
        mod = m.group(1)
        return f"swingbot.core.{MAP[mod]}.{mod}" if mod in MAP else m.group(0)

    text = re.sub(r"swingbot\.core\.([a-z_][a-z0-9_]*)\b", _dotted, text)

    # Form 4: the package-attribute import. Must split a comma list whose names
    # land in different packages.
    #
    # The parenthesised form `from swingbot.core import (\n  a,\n  b,\n)` does
    # not exist in the repo today. Guard rather than handle it: the regex below
    # excludes "(", so such a line would be SKIPPED SILENTLY and ship a broken
    # import. Fail loudly instead and hand-edit the one line.
    if re.search(r"^[ \t]*from swingbot\.core import \(", text, flags=re.M):
        raise SystemExit(
            "parenthesised 'from swingbot.core import (...)' found; "
            "rewrite it as a single line by hand, then re-run")

    def _pkg_attr(m: re.Match) -> str:
        indent, names = m.group(1), m.group(2)
        groups: dict[str, list[str]] = {}
        for spec in (n.strip() for n in names.split(",")):
            mod = spec.split()[0]              # "data as data_module" -> "data"
            groups.setdefault(MAP.get(mod, ""), []).append(spec)
        lines = []
        for pkg, specs in groups.items():
            target = f"swingbot.core.{pkg}" if pkg else "swingbot.core"
            lines.append(f"{indent}from {target} import {', '.join(specs)}")
        return "\n".join(lines)

    text = re.sub(r"^([ \t]*)from swingbot\.core import ([^\n(]+)$",
                  _pkg_attr, text, flags=re.M)

    # Form 5: relative imports, one dot (sibling) or two (parent), including
    # the `from .. import MOD` package-attribute variant.
    def _rel(m: re.Match) -> str:
        indent, mod = m.group(1), m.group(2)
        return (f"{indent}from swingbot.core.{MAP[mod]}.{mod} import"
                if mod in MAP else m.group(0))

    text = re.sub(r"^([ \t]*)from \.\.?([a-z_][a-z0-9_]*) import", _rel,
                  text, flags=re.M)

    def _rel_attr(m: re.Match) -> str:
        indent, mod = m.group(1), m.group(2)
        return (f"{indent}from swingbot.core.{MAP[mod]} import {mod}"
                if mod in MAP else m.group(0))

    text = re.sub(r"^([ \t]*)from \.\.? import ([a-z_][a-z0-9_]*)$", _rel_attr,
                  text, flags=re.M)
    return text


def main(pkg: str) -> None:
    if pkg not in _LAYOUT:
        raise SystemExit(f"unknown package {pkg!r}; expected one of {list(_LAYOUT)}")

    dest = ROOT / "swingbot" / "core" / pkg
    dest.mkdir(exist_ok=True)
    init = dest / "__init__.py"
    if not init.exists():
        init.write_text("", encoding="utf-8")
        subprocess.run(["git", "add", str(init)], cwd=ROOT, check=True)

    moved = []
    for mod in _LAYOUT[pkg].split():
        src = ROOT / "swingbot" / "core" / f"{mod}.py"
        if not src.exists():
            print(f"  skip {mod}.py (already moved or absent)")
            continue
        subprocess.run(["git", "mv", str(src), str(dest / f"{mod}.py")],
                       cwd=ROOT, check=True)
        moved.append(mod)
    print(f"moved {len(moved)} modules into swingbot/core/{pkg}/")

    changed = 0
    for path in source_files():
        before = path.read_text(encoding="utf-8")
        after = rewrite(before)
        if after != before:
            path.write_text(after, encoding="utf-8")
            changed += 1
    print(f"rewrote references in {changed} files")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    main(sys.argv[1])
