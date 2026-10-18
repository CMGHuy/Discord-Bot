#!/usr/bin/env python3
"""Resolve the admin's design tokens and write the cross-language fixture.

    python scripts/dev/dump_tokens.py           # rewrite tests/charts/resolved_tokens.json
    python scripts/dev/dump_tokens.py --check   # exit 1 when the fixture is stale

Spec v167 § 1. Tokens come in three tiers: palette.css holds raw named colours
(tier 1); tokens.css maps meanings onto them through var() (tier 2) and builds
component tokens on top (tier 3). Anything that needs a literal -- the Discord
chart THEME (tests/charts/test_chart_theme.py), the jsdom test document
(frontend/src/test-setup.ts) and the contrast / chart-palette gates -- reads
the resolved values. Two resolvers exist, this one and
frontend/src/app/ui/testing/resolve-token.ts; both must reproduce the
committed fixture exactly, so neither can drift and no token edit can land
without regenerating it.

Rules (resolve-token.ts mirrors them): comments are stripped; only top-level
`:root { }` blocks are read, so every @media / @supports override is dropped;
declarations apply in file order, later wins; names lose their leading `--`;
values are whitespace-collapsed; `var(--x)` is followed recursively. An
undefined reference, a cycle or a `var(--x, fallback)` is an error.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_STYLES = REPO / "frontend" / "src" / "styles"
STYLE_FILES: tuple[Path, Path] = (_STYLES / "palette.css", _STYLES / "tokens.css")
FIXTURE = REPO / "tests" / "charts" / "resolved_tokens.json"

_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_VAR_RE = re.compile(r"var\(--([\w-]+)\)")
_WS_RE = re.compile(r"\s+")


def strip_comments(css: str) -> str:
    return _COMMENT_RE.sub("", css)


def _block_end(css: str, open_brace: int) -> int:
    """Index just past the `}` that closes the block opened at `open_brace`."""
    depth = 0
    for index in range(open_brace, len(css)):
        depth += {"{": 1, "}": -1}.get(css[index], 0)
        if depth == 0:
            return index + 1
    raise ValueError(f"unbalanced braces from offset {open_brace}")


def _top_level_blocks(css: str):
    """(selector, body) for each top-level `selector { body }`, in file order."""
    start = 0
    while (open_brace := css.find("{", start)) >= 0:
        end = _block_end(css, open_brace)
        selector = css[start:open_brace].rsplit(";", 1)[-1].strip()
        yield selector, css[open_brace + 1:end - 1]
        start = end


def _declarations(body: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for chunk in body.split(";"):
        name, colon, value = chunk.partition(":")
        name = name.strip()
        if colon and name.startswith("--"):
            found[name[2:]] = _WS_RE.sub(" ", value).strip()
    return found


def parse_root(css: str) -> dict[str, str]:
    """Every custom property declared in a top-level `:root` block."""
    declared: dict[str, str] = {}
    for selector, body in _top_level_blocks(strip_comments(css)):
        if selector == ":root":
            declared.update(_declarations(body))
    return declared


def resolve(declared: dict[str, str]) -> dict[str, str]:
    """Follow every `var(--x)` hop to a literal."""
    resolved: dict[str, str] = {}

    def visit(name: str, trail: tuple[str, ...]) -> str:
        if name in resolved:
            return resolved[name]
        if name not in declared:
            raise KeyError(f"--{name} is not defined")
        if name in trail:
            raise ValueError(f"cycle at --{name}")
        value = _VAR_RE.sub(lambda m: visit(m.group(1), trail + (name,)), declared[name])
        if "var(" in value:
            raise ValueError(f"--{name}: only plain var(--x) is supported, got {declared[name]!r}")
        resolved[name] = value
        return value

    for name in declared:
        visit(name, ())
    return resolved


def resolve_tokens(paths: tuple[Path, ...] = STYLE_FILES) -> dict[str, str]:
    """Merge the files in order, resolve, and return sorted by name."""
    declared: dict[str, str] = {}
    for path in paths:
        declared.update(parse_root(path.read_text(encoding="utf-8")))
    resolved = resolve(declared)
    return {name: resolved[name] for name in sorted(resolved)}


def _render(tokens: dict[str, str]) -> bytes:
    # Bytes, not write_text: on Windows write_text would emit CRLF.
    return (json.dumps(tokens, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _first_difference(committed: dict[str, str], current: dict[str, str]) -> str | None:
    for name in sorted(set(committed) | set(current)):
        if committed.get(name) != current.get(name):
            return name
    return None


def _check(tokens: dict[str, str]) -> int:
    committed = json.loads(FIXTURE.read_text(encoding="utf-8")) if FIXTURE.exists() else {}
    name = _first_difference(committed, tokens)
    if name is None:
        print(f"{FIXTURE.name} is current ({len(tokens)} tokens)")
        return 0
    print(f"{FIXTURE.name} is stale at --{name}: fixture has {committed.get(name)!r}, "
          f"the CSS resolves to {tokens.get(name)!r}. Run: python scripts/dev/dump_tokens.py")
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve the admin design tokens.")
    parser.add_argument("--check", action="store_true", help="exit 1 when the fixture is stale")
    args = parser.parse_args(argv)
    # STYLE_FILES / FIXTURE are read at call time, so tests can point them elsewhere.
    tokens = resolve_tokens(STYLE_FILES)
    if args.check:
        return _check(tokens)
    FIXTURE.write_bytes(_render(tokens))
    print(f"wrote {len(tokens)} tokens to {FIXTURE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
