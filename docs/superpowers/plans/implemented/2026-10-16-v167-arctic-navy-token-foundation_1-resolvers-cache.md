# v167 Arctic Navy token foundation. Part 1: resolvers, fixture, chart cache, supersede marks (AN1..AN6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Never read this part whole**: `grep -n "^### Task AN3:" -A 300 docs/superpowers/plans/2026-10-16-v167-arctic-navy-token-foundation_1-resolvers-cache.md`.

**Spec:** [`docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md`](../specs/2026-10-16-v167-arctic-navy-token-foundation-design.md) (this part: § 1 three tiers, shared resolver, fixture, test selection; § 4 chart cache `STYLE_VERSION`; § 5 `contrast.spec.ts` / `chart-palette.spec.ts` / `test_chart_theme.py` helper rows; § 6 superseded rules in specs v54 and v80; Amendments 1, 6, 7, 8)
**Index:** [`2026-10-16-v167-arctic-navy-token-foundation_0-index.md`](2026-10-16-v167-arctic-navy-token-foundation_0-index.md) carries the header (`Bump`, `Edge`, `Screen`), `## Global Constraints`, `## Review Focus`, `## Parallelisation` and the task ledger. Every task below implicitly includes the Global Constraints.

**Paths.** `$R` = `E:/Documents/Private/Projects/Discord-Bot` (main tree), `$WT` = `$R/.claude/worktrees/2026-10-16-v167-arctic-navy-token-foundation` (created in AN1 Step 1). Never `cd`; use `git -C $WT`, `python $WT/scripts/dev/testrun.py file <test>` and `npm --prefix $WT/frontend exec -- ng test --watch=false --include <spec>`. All file paths below are relative to `$WT` unless they say `$R`.

**`GATES`** (from the index) = `--include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts`, plus `--include src/app/ui/resolve-token.spec.ts` once AN3 has created it.

**Order.** AN1 first (worktree). Then AN2 and AN6 in parallel. AN3 after AN2; AN4 after AN3. AN5 after AN2 (same file `test_chart_theme.py`), in parallel with AN3/AN4.

**What this part leaves unchanged on purpose.** No colour value changes in this part: `palette.css` is created empty, `tokens.css` is not edited, `THEME` keeps today's hexes, and `STYLE_VERSION` starts at `"v80"`. The palette swap is AN7 (part 2), which needs every reader already on the resolver.

---

# Phase 1 — Plumbing: escalation, resolvers, fixture

### Task AN1: Worktree; widen the render-tier escalation prefix to `frontend/src/styles/`

**Model:** haiku — a one-line tuple change plus one copied test case

**Files:**
- Modify: `scripts/dev/select_tests.py` (`ESCALATE_PREFIXES` :222-225)
- Modify: `tests/scripts/test_testrun_escalation.py` (one test appended)

**Interfaces:**
- Consumes: nothing from this plan. From `main`: `select_tests.ESCALATE_PREFIXES` (tuple of path prefixes, re-exported by `testrun.py:57`), `testrun.should_escalate() -> tuple[bool, str]`, `testrun.changed_paths()`.
- Produces: `ESCALATE_PREFIXES = ("swingbot/core/charts/", "frontend/src/styles/")`; test `test_a_palette_edit_escalates_fast_to_full`; the worktree `$WT` on branch `2026-10-16-v167-arctic-navy-token-foundation` with `frontend/node_modules` installed (every later task uses it).

Why (spec § 1, Test selection): `tests/charts/test_chart_theme.py` is `pytestmark = slow`. Today only `frontend/src/styles/tokens.css` escalates `testrun.py fast` to the full run, so an edit to the new `palette.css` alone would let `fast` skip the PNG lockstep check. `testrun.py:118` reads the imported tuple, so `select_tests.py` is the only edit.

- [ ] **Step 1: Create the worktree**

Invoke the `worktree-lifecycle` skill. Reuse the worktree if `git -C E:/Documents/Private/Projects/Discord-Bot worktree list` already shows `2026-10-16-v167-arctic-navy-token-foundation` (then skip to Step 2). Otherwise:

```bash
git -C E:/Documents/Private/Projects/Discord-Bot fetch --quiet origin
git -C E:/Documents/Private/Projects/Discord-Bot worktree add .claude/worktrees/2026-10-16-v167-arctic-navy-token-foundation -b 2026-10-16-v167-arctic-navy-token-foundation main
git -C E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v167-arctic-navy-token-foundation log --oneline -1
npm --prefix E:/Documents/Private/Projects/Discord-Bot/.claude/worktrees/2026-10-16-v167-arctic-navy-token-foundation/frontend ci
```

Expected: the log line is the current `main` HEAD (the commit that carries this plan); `npm ci` ends without `ERR!`. Every later step runs in `$WT`.

- [ ] **Step 2: Write the failing test**

Append to `tests/scripts/test_testrun_escalation.py` (after `test_a_token_edit_escalates_fast_to_full`, before `test_the_deleted_admin_palette_is_no_longer_a_trigger` is fine too; append at the end of the file):

```python


def test_a_palette_edit_escalates_fast_to_full(monkeypatch):
    """Spec v167 § 1: tier 1 lives in frontend/src/styles/palette.css, and
    test_chart_theme.py resolves THEME through it. A palette-only edit must
    escalate `fast` just as a tokens.css edit does."""
    import testrun

    monkeypatch.setattr(testrun, "changed_paths", lambda: ["frontend/src/styles/palette.css"])
    escalate, reason = testrun.should_escalate()
    assert escalate
    assert "frontend/src/styles/palette.css" in reason
```

- [ ] **Step 3: Run it to verify it fails**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_testrun_escalation.py`
Expected: `1 failed, 3 passed` — `test_a_palette_edit_escalates_fast_to_full` fails on `assert escalate` (`palette.css` matches no prefix yet).

- [ ] **Step 4: Widen the prefix**

In `scripts/dev/select_tests.py`, replace:

```python
ESCALATE_PREFIXES = (
    "swingbot/core/charts/",
    "frontend/src/styles/tokens.css",
)
```

with:

```python
ESCALATE_PREFIXES = (
    "swingbot/core/charts/",
    # The whole token directory, not one file: palette.css (tier 1) and
    # tokens.css (tiers 2 and 3) both feed test_chart_theme.py through the
    # resolver (spec v167 § 1). fonts.css rides along; it is rarely edited.
    "frontend/src/styles/",
)
```

- [ ] **Step 5: Run the escalation tests and the profile test that pins the shared tuple**

Run: `python $WT/scripts/dev/testrun.py file tests/scripts/test_testrun_escalation.py`
Expected: `4 passed`. (The existing `test_a_token_edit_escalates_fast_to_full` still passes because `frontend/src/styles/tokens.css` starts with the new prefix; `test_an_unrelated_frontend_edit_does_not_escalate` still passes because `frontend/src/app/ui/chip.ts` does not.)

Run: `python $WT/scripts/dev/testrun.py file tests/dev/test_testrun_changed_profile.py`
Expected: `N passed`, `0 failed` (it asserts `testrun.ESCALATE_PREFIXES is select_tests.ESCALATE_PREFIXES`; identity is untouched).

Quote both verdict lines in the report.

- [ ] **Step 6: Commit**

```bash
git -C $WT add scripts/dev/select_tests.py tests/scripts/test_testrun_escalation.py
git -C $WT commit -m "test(v167): escalate fast to full on any frontend/src/styles/ edit

palette.css (tier 1, created next) feeds test_chart_theme.py through the
token resolver; a palette-only edit must not let the fast tier skip it.

Narrow run: <paste the '4 passed' line>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN2: Python token resolver, `dump_tokens.py`, committed fixture; empty `palette.css` wired into `styles.css` and the chart harness; `test_chart_theme.py` on `_resolve()`

**Model:** sonnet — a small parser plus fixture and test rewiring, rules fixed by the spec

**Files:**
- Create: `scripts/dev/dump_tokens.py`
- Create: `tests/dev/test_dump_tokens.py`
- Create: `tests/charts/resolved_tokens.json` (generated, never hand-edited)
- Create: `frontend/src/styles/palette.css`
- Modify: `frontend/src/styles.css` (`@import` block :3-4)
- Modify: `frontend/chart-harness/index.html` (stylesheet link :6)
- Modify: `tests/charts/test_chart_theme.py` (docstring :1-8, imports :9-13, `TOKENS_CSS` :25, `_tokens()` :82-85, `test_theme_matches_the_admin_tokens_byte_for_byte` :117-120, one new test)

**Interfaces:**
- Consumes: AN1's worktree. From `main`: `frontend/src/styles/tokens.css` (one `:root` block :19-280, three `@media` blocks after it), `cs.THEME` (16 keys, lower-case hex values).
- Produces (consumed by AN3, AN5, AN7, AN8 and every later token edit):
  - `scripts/dev/dump_tokens.py`: `REPO: Path`; `STYLE_FILES: tuple[Path, Path]` = (`frontend/src/styles/palette.css`, `frontend/src/styles/tokens.css`), in that order; `FIXTURE: Path` = `tests/charts/resolved_tokens.json`; `strip_comments(css: str) -> str`; `parse_root(css: str) -> dict[str, str]`; `resolve(declared: dict[str, str]) -> dict[str, str]`; `resolve_tokens(paths=STYLE_FILES) -> dict[str, str]`; `main(argv: list[str] | None = None) -> int`.
  - Rules (AN3's TypeScript port must match them exactly): comments stripped first; only top-level blocks whose selector is exactly `:root` are read, so every `@media` / `@supports` block is dropped; every `--name: value;` declaration in file order, later wins; keys **without** the leading `--`; values whitespace-collapsed to single spaces and stripped; `var(--x)` replaced recursively; an undefined reference raises `KeyError("--x is not defined")`; a cycle raises `ValueError("cycle at --x")`; fallback syntax `var(--x, y)` raises `ValueError` (unsupported).
  - Fixture shape: `{"<name without -->": "<resolved value>"}`, keys sorted, `indent=2`, LF line endings, trailing newline. Today 65 entries (every current `tokens.css` token; tier 1 is empty until AN7).
  - `frontend/src/styles/palette.css`: header comment + empty `:root {\n}`. `styles.css` imports it between `fonts.css` and `tokens.css`.
  - `tests/charts/test_chart_theme.py`: `_resolve() -> dict[str, str]` (values lower-cased); `_tokens()` and `TOKENS_CSS` removed; new `test_resolver_reproduces_the_committed_fixture`.

- [ ] **Step 1: Write the failing resolver tests**

Create `tests/dev/test_dump_tokens.py`:

```python
"""scripts/dev/dump_tokens.py: the Python half of the token resolver pair
(spec v167 § 1). frontend/src/app/ui/resolve-token.spec.ts holds the
TypeScript half to the same committed fixture."""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))

import dump_tokens as dt  # noqa: E402


def test_strip_comments_removes_block_comments_across_lines():
    assert dt.strip_comments("a /* x\n { y } */ b") == "a  b"


def test_parse_root_reads_every_root_block_and_later_wins():
    css = ":root { --a: #111; --b: 1px; }\n:root {\n  --a:   #222 ;\n}\n"
    assert dt.parse_root(css) == {"a": "#222", "b": "1px"}


def test_parse_root_drops_media_and_supports_blocks():
    css = (":root { --gap: 14px; }\n"
           "@media (max-width: 639px) { :root { --gap: 10px; } }\n"
           "@supports (color: color-mix(in srgb, red, blue)) { :root { --x: 1; } }\n")
    assert dt.parse_root(css) == {"gap": "14px"}


def test_parse_root_ignores_comments_and_non_root_rules():
    css = "/* :root { --ghost: 1; } */ body { --local: 2; } :root { --kept: 3; }"
    assert dt.parse_root(css) == {"kept": "3"}


def test_parse_root_collapses_whitespace_in_values():
    css = ":root { --shadow: 0 8px 24px\n      rgba(0, 0, 0, .55); }"
    assert dt.parse_root(css) == {"shadow": "0 8px 24px rgba(0, 0, 0, .55)"}


def test_resolve_follows_var_hops_to_a_literal():
    declared = {"navy": "#070b14", "bg": "var(--navy)", "scrim": "var(--bg)",
                "gap": "calc(2px * var(--scale))", "scale": "1"}
    assert dt.resolve(declared) == {"navy": "#070b14", "bg": "#070b14", "scrim": "#070b14",
                                    "gap": "calc(2px * 1)", "scale": "1"}


def test_resolve_names_an_undefined_reference():
    with pytest.raises(KeyError, match="--missing is not defined"):
        dt.resolve({"bg": "var(--missing)"})


def test_resolve_rejects_a_cycle():
    with pytest.raises(ValueError, match="cycle at --a"):
        dt.resolve({"a": "var(--b)", "b": "var(--a)"})


def test_resolve_rejects_fallback_syntax():
    with pytest.raises(ValueError, match="only plain var"):
        dt.resolve({"a": "#fff", "b": "var(--a, #000)"})


def test_resolve_tokens_merges_files_in_order_and_sorts(tmp_path):
    palette = tmp_path / "palette.css"
    tokens = tmp_path / "tokens.css"
    palette.write_text(":root { --navy-950: #070b14; }", encoding="utf-8")
    tokens.write_text(":root { --bg: var(--navy-950); --accent: #7cc4ff; }", encoding="utf-8")
    result = dt.resolve_tokens((palette, tokens))
    assert result == {"accent": "#7cc4ff", "bg": "#070b14", "navy-950": "#070b14"}
    assert list(result) == sorted(result)


def _point_at(monkeypatch, tmp_path, css):
    tokens = tmp_path / "tokens.css"
    tokens.write_text(css, encoding="utf-8")
    monkeypatch.setattr(dt, "STYLE_FILES", (tokens,))
    monkeypatch.setattr(dt, "FIXTURE", tmp_path / "resolved_tokens.json")


def test_main_writes_the_fixture_and_check_passes_on_it(monkeypatch, tmp_path):
    _point_at(monkeypatch, tmp_path, ":root { --b: 2px; --a: var(--b); }")
    assert dt.main([]) == 0
    assert (tmp_path / "resolved_tokens.json").read_bytes() == b'{\n  "a": "2px",\n  "b": "2px"\n}\n'
    assert dt.main(["--check"]) == 0


def test_check_fails_and_names_the_first_stale_token(monkeypatch, tmp_path, capsys):
    _point_at(monkeypatch, tmp_path, ":root { --a: 1px; }")
    dt.main([])
    (tmp_path / "tokens.css").write_text(":root { --a: 2px; }", encoding="utf-8")
    assert dt.main(["--check"]) == 1
    assert "--a" in capsys.readouterr().out


def test_the_committed_fixture_is_current():
    """A palette.css / tokens.css edit without `python scripts/dev/dump_tokens.py`
    fails here, in the fast tier (test_chart_theme.py runs only in the slow tier)."""
    assert dt.main(["--check"]) == 0
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: collection error, `ModuleNotFoundError: No module named 'dump_tokens'`.

- [ ] **Step 3: Write `scripts/dev/dump_tokens.py`**

```python
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
```

- [ ] **Step 4: Run the tests; every one passes except the committed-fixture check**

Run: `python $WT/scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: `1 failed, 12 passed`. `test_the_committed_fixture_is_current` fails because `palette.css` does not exist yet (`FileNotFoundError`).

- [ ] **Step 5: Create the empty tier-1 file**

Create `frontend/src/styles/palette.css`:

```css
/* Tier 1: the palette (spec v167 § 1).
 *
 * Raw named colours. This is the ONLY file under frontend/src allowed to hold
 * a hued colour literal. The exceptions are fixed and gated: --chart-1..6 and
 * --quality-4 stay literal hex in tokens.css (jsdom and chart-palette.spec.ts
 * read them, see the comment there), and index.html / manifest.webmanifest
 * carry copies of the resolved --bg for the cold load.
 *
 * Names say what a colour IS (--navy-950, --mint-400-a12), never what it MEANS
 * (--surface, --pos-soft): meaning is tier 2, in tokens.css, which refers to
 * these through var(). Components never read this file's names directly.
 *
 * After every edit: `python scripts/dev/dump_tokens.py`, and commit
 * tests/charts/resolved_tokens.json in the same commit.
 */
:root {
}
```

- [ ] **Step 6: Import it before the tokens, in the app and in the chart harness**

In `frontend/src/styles.css`, replace:

```css
@import './styles/fonts.css';
@import './styles/tokens.css';
```

with:

```css
@import './styles/fonts.css';
/* Tier 1 before tiers 2 and 3: tokens.css refers to these names (spec v167 § 1). */
@import './styles/palette.css';
@import './styles/tokens.css';
```

In `frontend/chart-harness/index.html`, replace:

```html
    <link rel="stylesheet" href="../src/styles/tokens.css" />
```

with:

```html
    <link rel="stylesheet" href="../src/styles/palette.css" />
    <link rel="stylesheet" href="../src/styles/tokens.css" />
```

- [ ] **Step 7: Generate the fixture and run the resolver tests**

Run: `python $WT/scripts/dev/dump_tokens.py`
Expected: `wrote 65 tokens to ...resolved_tokens.json`.

Spot-check the file (it must hold today's values; nothing has changed colour yet):

Run: `grep -n '"bg"\|"pos-soft"\|"radius"\|"scrim"\|"text-hero"' $WT/tests/charts/resolved_tokens.json`
Expected, in key order:

```
  "bg": "#0c0f16",
  "pos-soft": "rgba(23, 201, 142, 0.12)",
  "radius": "2px",
  "scrim": "rgba(12, 15, 22, .72)",
  "text-hero": "calc(44px * 1)",
```

Run: `python $WT/scripts/dev/testrun.py file tests/dev/test_dump_tokens.py`
Expected: `13 passed`.

- [ ] **Step 8: Move `test_chart_theme.py` onto the resolver**

In `tests/charts/test_chart_theme.py`:

Replace the module docstring (the `"""..."""` under the `# tests/charts/test_chart_theme.py` comment line, which stays) with:

```python
"""The Discord chart palette is the admin palette (spec v80 D5, spec v167 § 4).

`chart_style.THEME` copies the frontend tokens it names. This file resolves
them through scripts/dev/dump_tokens.py (palette.css then tokens.css, every
var() hop followed to a literal) and holds every chart colour to D5's rules:
it is a D1 token or a D2 series, it is not confusable with gain or loss, and
roles drawn together are distinct.
"""
```

Add `import json` and `import sys` to the standard-library imports, so the block reads:

```python
import ast
import itertools
import json
import math
import re
import sys
from pathlib import Path
```

(`re` stays: `_HEX` at :137 uses it.)

Replace:

```python
REPO = Path(__file__).resolve().parents[2]
TOKENS_CSS = REPO / "frontend" / "src" / "styles" / "tokens.css"
```

with:

```python
REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "dev"))

import dump_tokens  # noqa: E402  (scripts/dev is not a package)
```

Replace `_tokens()`:

```python
def _tokens() -> dict[str, str]:
    css = TOKENS_CSS.read_text(encoding="utf-8")
    return {name: value.lower()
            for name, value in re.findall(r"^\s*--([\w-]+):\s*(#[0-9a-fA-F]{6});", css, flags=re.M)}
```

with:

```python
def _resolve() -> dict[str, str]:
    """Every admin token with its var() hops followed to a literal (spec v167 § 1).

    Not a private regexp over tokens.css: once tier 2 is var(--palette-name),
    a hex-only match finds nothing. One resolver per language, both held to
    tests/charts/resolved_tokens.json."""
    return {name: value.lower() for name, value in dump_tokens.resolve_tokens().items()}
```

Replace:

```python
def test_theme_matches_the_admin_tokens_byte_for_byte():
    tokens = _tokens()
    for name, value in cs.THEME.items():
        assert tokens[name] == value.lower(), name
```

with:

```python
def test_theme_matches_the_admin_tokens_byte_for_byte():
    tokens = _resolve()
    for name, value in cs.THEME.items():
        assert tokens[name] == value.lower(), name


def test_resolver_reproduces_the_committed_fixture():
    """frontend/src/app/ui/resolve-token.spec.ts holds the TypeScript resolver
    to the same file, so the two resolvers cannot drift apart unnoticed and a
    token edit without regenerating fails here (spec v167 § 1)."""
    fixture = json.loads(dump_tokens.FIXTURE.read_text(encoding="utf-8"))
    assert dump_tokens.resolve_tokens() == fixture
```

Confirm nothing else read the removed names: `git -C $WT grep -n "_tokens()\|TOKENS_CSS" -- tests/charts/test_chart_theme.py` prints nothing.

- [ ] **Step 9: Run the chart-theme test and the frontend gates**

Run: `python $WT/scripts/dev/testrun.py file tests/charts/test_chart_theme.py`
Expected: `N passed`, `0 failed` (one test more than before; `test_theme_matches_the_admin_tokens_byte_for_byte` passes on today's values).

`styles.css` changed, so run the gates (no spec reads `palette.css` yet; this proves the import disturbed nothing):

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: `Tests  N passed`, no failures. (A 60 s `Timeout waiting for worker` with no tests run is machine load: re-run once.)

Run: `python $WT/scripts/dev/dump_tokens.py --check`
Expected: `resolved_tokens.json is current (65 tokens)`, exit 0.

- [ ] **Step 10: Complexity**

Run: `python -m radon cc -s -n C $WT/scripts/dev/dump_tokens.py $WT/tests/charts/test_chart_theme.py $WT/tests/dev/test_dump_tokens.py`
Expected: no output (every function below grade C, so < 11).

- [ ] **Step 11: Commit**

```bash
git -C $WT add scripts/dev/dump_tokens.py tests/dev/test_dump_tokens.py tests/charts/resolved_tokens.json frontend/src/styles/palette.css frontend/src/styles.css frontend/chart-harness/index.html tests/charts/test_chart_theme.py
git -C $WT commit -m "feat(v167): Python token resolver, resolved-token fixture, empty tier-1 palette.css

dump_tokens.py follows var() hops through palette.css then tokens.css and
writes tests/charts/resolved_tokens.json; --check fails on a stale fixture.
test_chart_theme.py compares THEME through the resolver instead of a
hex-only regexp. palette.css is imported before tokens.css in styles.css
and the chart harness; it stays empty until the Arctic Navy swap.

Narrow runs: <test_dump_tokens '13 passed'>, <test_chart_theme verdict>, <GATES 'Tests  N passed'>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN3: TypeScript resolver `resolve-token.ts`, its spec against the fixture, flattened `:root` injected by `test-setup.ts`

**Model:** sonnet — a port of AN2's parser plus the jsdom injection, whole frontend suite as check

**Files:**
- Create: `frontend/src/app/ui/testing/resolve-token.ts`
- Create: `frontend/src/app/ui/resolve-token.spec.ts`
- Modify: `frontend/src/test-setup.ts` (whole body :1-42)
- Modify: `frontend/src/app/ui/tokens.spec.ts` (`offers a hero size above the primary metric size` :281-289 only; see Step 6 for why)

**Interfaces:**
- Consumes: AN2's `tests/charts/resolved_tokens.json` (shape `{"<name without -->": "<literal>"}`, sorted) and `frontend/src/styles/palette.css`; AN2's resolver rules (listed in AN2 Interfaces), which this port must match exactly.
- Produces (consumed by AN4, AN7, AN8, AN11 and every spec that needs a token value):
  - `STYLE_FILES = ['src/styles/palette.css', 'src/styles/tokens.css'] as const`
  - `FIXTURE_PATH = '../tests/charts/resolved_tokens.json'` (relative to `process.cwd()`, which `ng test` sets to `frontend/`)
  - `stripComments(css: string): string`
  - `parseRoot(css: string): Record<string, string>` (keys without `--`)
  - `resolveAll(declared: Record<string, string>): Record<string, string>` (throws `Error('--x is not defined')`, `Error('cycle at --x')`, and on fallback syntax `Error('--x: only plain var(--x) is supported')`)
  - `resolvedTokens(): Record<string, string>` (reads `STYLE_FILES` with `readFileSync(join(process.cwd(), f), 'utf8')`, memoised, keys sorted)
  - `resolveToken(name: string): string` (accepts `--x` or `x`; throws `Error('<name> is not a token')`)
  - `readFixture(): Record<string, string>`
  - `flattenedRootCss(tokens: Record<string, string>): string` (`:root {\n  --a: v;\n  --b: w;\n}\n`, keys sorted)
  - `src/test-setup.ts` injects `flattenedRootCss(readFixture())` instead of the raw `tokens.css`, so jsdom never sees a nested `var()` (spec Amendment 1).

Why the injection changes (spec Amendment 1): from AN7 on, tier 2 is `--pos: var(--mint-400)`. jsdom resolves neither a nested `var()` inside a custom property nor `color-mix()`, so `chartPalette()` (which reads `--pos`, `--pos-soft`, … through `getComputedStyle`) would hand lightweight-charts the string `var(--mint-400)`. A flattened `:root` of literals keeps every runtime token read real under test; the browser still loads the tiers.

- [ ] **Step 1: Write the failing spec**

Create `frontend/src/app/ui/resolve-token.spec.ts`:

```ts
import { describe, expect, it } from 'vitest';

import {
  flattenedRootCss,
  parseRoot,
  readFixture,
  resolveAll,
  resolvedTokens,
  resolveToken,
  stripComments,
} from './testing/resolve-token';

/**
 * Spec v167 § 1: one token resolver per language, each held to the committed
 * fixture tests/charts/resolved_tokens.json. scripts/dev/dump_tokens.py writes
 * it and tests/charts/test_chart_theme.py holds the Python resolver to it, so a
 * drift in either resolver, or a palette.css / tokens.css edit without
 * regenerating, fails a test in both languages.
 */
describe('the TypeScript token resolver', () => {
  it('reproduces the committed fixture exactly', () => {
    expect(resolvedTokens()).toEqual(readFixture());
  });

  it('accepts a name with or without the leading dashes', () => {
    expect(resolveToken('--bg')).toBe(resolveToken('bg'));
    expect(resolveToken('--bg')).toMatch(/^#[0-9a-f]{6}$/i);
  });

  it('names a token that does not exist', () => {
    expect(() => resolveToken('--no-such-token')).toThrow('--no-such-token is not a token');
  });

  it('never hands back a nested var()', () => {
    for (const [name, value] of Object.entries(resolvedTokens())) {
      expect(value, name).not.toContain('var(');
    }
  });
});

/** The same cases as tests/dev/test_dump_tokens.py, so the two ports agree on the rules. */
describe('parseRoot and resolveAll follow the dump_tokens.py rules', () => {
  it('strips block comments across lines', () => {
    expect(stripComments('a /* x\n { y } */ b')).toBe('a  b');
  });

  it('reads every :root block, later wins', () => {
    expect(parseRoot(':root { --a: #111; --b: 1px; }\n:root {\n  --a:   #222 ;\n}\n')).toEqual({
      a: '#222',
      b: '1px',
    });
  });

  it('drops @media and @supports blocks', () => {
    const css =
      ':root { --gap: 14px; }\n' +
      '@media (max-width: 639px) { :root { --gap: 10px; } }\n' +
      '@supports (color: color-mix(in srgb, red, blue)) { :root { --x: 1; } }\n';
    expect(parseRoot(css)).toEqual({ gap: '14px' });
  });

  it('ignores comments and non-root rules', () => {
    expect(parseRoot('/* :root { --ghost: 1; } */ body { --local: 2; } :root { --kept: 3; }')).toEqual({
      kept: '3',
    });
  });

  it('collapses whitespace in values', () => {
    expect(parseRoot(':root { --shadow: 0 8px 24px\n      rgba(0, 0, 0, .55); }')).toEqual({
      shadow: '0 8px 24px rgba(0, 0, 0, .55)',
    });
  });

  it('follows var() hops to a literal', () => {
    const declared = {
      navy: '#070b14',
      bg: 'var(--navy)',
      scrim: 'var(--bg)',
      gap: 'calc(2px * var(--scale))',
      scale: '1',
    };
    expect(resolveAll(declared)).toEqual({
      navy: '#070b14',
      bg: '#070b14',
      scrim: '#070b14',
      gap: 'calc(2px * 1)',
      scale: '1',
    });
  });

  it('names an undefined reference', () => {
    expect(() => resolveAll({ bg: 'var(--missing)' })).toThrow('--missing is not defined');
  });

  it('rejects a cycle', () => {
    expect(() => resolveAll({ a: 'var(--b)', b: 'var(--a)' })).toThrow('cycle at --a');
  });

  it('rejects fallback syntax', () => {
    expect(() => resolveAll({ a: '#fff', b: 'var(--a, #000)' })).toThrow('only plain var');
  });
});

describe('the jsdom test document (src/test-setup.ts)', () => {
  it('flattens to one :root block with sorted keys', () => {
    expect(flattenedRootCss({ b: '2px', a: '#fff' })).toBe(':root {\n  --a: #fff;\n  --b: 2px;\n}\n');
  });

  it('sees every token as its resolved literal', () => {
    const root = getComputedStyle(document.documentElement);
    for (const [name, value] of Object.entries(readFixture())) {
      expect(root.getPropertyValue(`--${name}`).trim(), name).toBe(value);
    }
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/resolve-token.spec.ts`
Expected: FAIL, the build cannot resolve `./testing/resolve-token`.

- [ ] **Step 3: Write `frontend/src/app/ui/testing/resolve-token.ts`**

`ui/testing/call-sites.ts` already uses `node:fs` from this directory, so the tsconfig already accepts it; nothing under `src/main.ts` imports `ui/testing/`, so it never reaches the app bundle.

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

/**
 * The TypeScript half of the token resolver pair (spec v167 § 1).
 *
 * Tier 1 (palette.css) holds raw colours; tier 2 and tier 3 (tokens.css) refer
 * to them through var(). A spec that needs a token's literal value -- contrast,
 * chart palette, chart theme -- asks this module, never a private regexp over
 * tokens.css, which stops matching the moment a token becomes a var().
 *
 * scripts/dev/dump_tokens.py is the Python half. The rules are identical, line
 * for line: comments stripped; only top-level `:root { }` blocks read (every
 * @media / @supports override dropped); file order, later wins; names without
 * the leading `--`; values whitespace-collapsed; `var(--x)` followed
 * recursively; an undefined reference, a cycle or a `var(--x, fallback)` is an
 * error. Both must reproduce tests/charts/resolved_tokens.json exactly
 * (resolve-token.spec.ts here, test_chart_theme.py there).
 *
 * Files are read from `process.cwd()` (= frontend/ under `ng test`), never
 * `import.meta.url` or `?raw`: see test-setup.ts for why both fail here.
 */
export const STYLE_FILES = ['src/styles/palette.css', 'src/styles/tokens.css'] as const;

/** Relative to `process.cwd()`, which `ng test` sets to frontend/. */
export const FIXTURE_PATH = '../tests/charts/resolved_tokens.json';

const COMMENT_RE = /\/\*[\s\S]*?\*\//g;
const VAR_RE = /var\(--([\w-]+)\)/g;

export function stripComments(css: string): string {
  return css.replace(COMMENT_RE, '');
}

/** Index just past the `}` that closes the block opened at `open`. */
function blockEnd(css: string, open: number): number {
  let depth = 0;
  for (let i = open; i < css.length; i++) {
    if (css[i] === '{') depth++;
    else if (css[i] === '}' && --depth === 0) return i + 1;
  }
  throw new Error(`unbalanced braces from offset ${open}`);
}

/** [selector, body] for each top-level `selector { body }`, in file order. */
function topLevelBlocks(css: string): [string, string][] {
  const blocks: [string, string][] = [];
  let start = 0;
  let open = css.indexOf('{', start);
  while (open >= 0) {
    const end = blockEnd(css, open);
    const selector = css.slice(start, open).split(';').pop()!.trim();
    blocks.push([selector, css.slice(open + 1, end - 1)]);
    start = end;
    open = css.indexOf('{', start);
  }
  return blocks;
}

function declarations(body: string): Record<string, string> {
  const found: Record<string, string> = {};
  for (const chunk of body.split(';')) {
    const colon = chunk.indexOf(':');
    const name = chunk.slice(0, Math.max(colon, 0)).trim();
    if (colon >= 0 && name.startsWith('--')) {
      found[name.slice(2)] = chunk.slice(colon + 1).replace(/\s+/g, ' ').trim();
    }
  }
  return found;
}

/** Every custom property declared in a top-level `:root` block. */
export function parseRoot(css: string): Record<string, string> {
  const declared: Record<string, string> = {};
  for (const [selector, body] of topLevelBlocks(stripComments(css))) {
    if (selector === ':root') Object.assign(declared, declarations(body));
  }
  return declared;
}

/** Follow every `var(--x)` hop to a literal. */
export function resolveAll(declared: Record<string, string>): Record<string, string> {
  const resolved: Record<string, string> = {};
  const visit = (name: string, trail: readonly string[]): string => {
    if (Object.hasOwn(resolved, name)) return resolved[name];
    if (!Object.hasOwn(declared, name)) throw new Error(`--${name} is not defined`);
    if (trail.includes(name)) throw new Error(`cycle at --${name}`);
    const value = declared[name].replace(VAR_RE, (_match, ref: string) => visit(ref, [...trail, name]));
    if (value.includes('var(')) throw new Error(`--${name}: only plain var(--x) is supported`);
    resolved[name] = value;
    return value;
  };
  for (const name of Object.keys(declared)) visit(name, []);
  return resolved;
}

function sortedByKey(tokens: Record<string, string>): Record<string, string> {
  return Object.fromEntries(Object.keys(tokens).sort().map((name) => [name, tokens[name]]));
}

let memo: Record<string, string> | undefined;

/** palette.css then tokens.css, resolved; read once per worker. */
export function resolvedTokens(): Record<string, string> {
  if (!memo) {
    const declared: Record<string, string> = {};
    for (const file of STYLE_FILES) {
      Object.assign(declared, parseRoot(readFileSync(join(process.cwd(), file), 'utf8')));
    }
    memo = sortedByKey(resolveAll(declared));
  }
  return memo;
}

/** The literal a token resolves to; `name` may carry its leading `--` or not. */
export function resolveToken(name: string): string {
  const key = name.startsWith('--') ? name.slice(2) : name;
  const tokens = resolvedTokens();
  if (!Object.hasOwn(tokens, key)) throw new Error(`${name} is not a token`);
  return tokens[key];
}

/** The committed fixture, as written by scripts/dev/dump_tokens.py. */
export function readFixture(): Record<string, string> {
  return JSON.parse(readFileSync(join(process.cwd(), FIXTURE_PATH), 'utf8')) as Record<string, string>;
}

/** One `:root` block of literals, keys sorted: what jsdom gets instead of the tiers. */
export function flattenedRootCss(tokens: Record<string, string>): string {
  const lines = Object.keys(tokens)
    .sort()
    .map((name) => `  --${name}: ${tokens[name]};`);
  return `:root {\n${lines.join('\n')}\n}\n`;
}
```

- [ ] **Step 4: Run the spec; only the jsdom case fails**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/resolve-token.spec.ts`
Expected: `1 failed`, the rest passed. The failure is `sees every token as its resolved literal`, on a token tier 2 builds from another one (for example `quality-1` reads back `var(--neg)`): `test-setup.ts` still injects the raw `tokens.css`, whose `var()` hops jsdom does not follow.

- [ ] **Step 5: Inject the flattened `:root` in `frontend/src/test-setup.ts`**

Replace the whole file with:

```ts
import { flattenedRootCss, readFixture } from './app/ui/testing/resolve-token';

/**
 * Put the real design tokens into the test document.
 *
 * Anything that paints to a canvas — the charts — cannot use `var(--pos)`; it
 * has to read the resolved value out of `getComputedStyle`. Without this file
 * that read comes back empty under jsdom, which is why `chart-theme.ts` used to
 * carry eight hex fallbacks. Those fallbacks were stale within one task of
 * being written (SR3's audit found them still holding the pre-SR2 palette), and
 * a stale fallback does not throw: it silently paints the previous design.
 *
 * **Flattened literals, not the CSS files (spec v167, Amendment 1).** Since
 * v167 the tokens come in tiers: palette.css holds the raw colours and
 * tokens.css refers to them (`--pos: var(--mint-400)`). jsdom resolves neither
 * a nested `var()` inside a custom property nor `color-mix()`, so injecting the
 * files would hand the charts the string `var(--mint-400)`. Instead this
 * injects one `:root` block of literals built from
 * tests/charts/resolved_tokens.json. The real browser still loads the tiers.
 *
 * **Generated, never copied by hand.** The fixture is written by
 * `python scripts/dev/dump_tokens.py`, and two tests keep it honest: the
 * TypeScript resolver must reproduce it (`ui/resolve-token.spec.ts`) and so
 * must the Python one (`tests/charts/test_chart_theme.py`). A token edit
 * without regenerating fails both, so this document cannot fall behind the
 * stylesheet the way the old fallbacks did.
 *
 * **`readFileSync`, not `import … from '…?raw'`.** `?raw` was tried first and
 * fails silently here in a way worth recording: the Angular compiler claims
 * every `.css` import ahead of Vite's `?raw` handler, the import resolves to an
 * **empty string**, and the injected `<style>` ends up empty — so every token
 * read still returns `''` and the only symptom is a chart with no colours.
 * `ui/tokens.spec.ts` hit the same wall and reads the file the same way.
 *
 * Resolved from `process.cwd()` rather than `import.meta.url`, for the reason
 * that file records: under `@angular/build:unit-test` the module's own URL is
 * an `http:` one, which `readFileSync` rejects. `ng test` always runs with the
 * frontend project root as its working directory.
 *
 * Appended to `<head>` on the shared jsdom document, once per worker. Nothing
 * removes it: every test in the process wants the tokens, and a per-test
 * teardown would only create an ordering rule to get wrong.
 */
const style = document.createElement('style');
style.textContent = flattenedRootCss(readFixture());
document.head.appendChild(style);
```

- [ ] **Step 6: Keep the hero-size case honest under flattened tokens**

`tokens.spec.ts` :281-289 reads `--text-hero` through `getComputedStyle` and asserts it still contains `var(--text-scale)`. With the flattened `:root` it reads `calc(44px * 1)`, so the case would fail for a reason that has nothing to do with the token. Its intent (the hero size scales with the zoom control) is a property of the source, so assert it there; `CSS` in that file is already the `tokens.css` text (:26).

In `frontend/src/app/ui/tokens.spec.ts`, replace:

```ts
  it('offers a hero size above the primary metric size', () => {
    const style = getComputedStyle(document.documentElement);
    const hero = style.getPropertyValue('--text-hero').trim();
    expect(hero).not.toBe('');
    // Same calc(px * var(--text-scale)) shape as every other size token, so
    // the zoom control reaches it too.
    expect(hero).toContain('var(--text-scale)');
  });
```

with:

```ts
  it('offers a hero size above the primary metric size', () => {
    const style = getComputedStyle(document.documentElement);
    expect(style.getPropertyValue('--text-hero').trim()).not.toBe('');
    // Same calc(px * var(--text-scale)) shape as every other size token, so
    // the zoom control reaches it too. Asserted on the source: the jsdom
    // document carries flattened literals (spec v167, Amendment 1), where
    // var(--text-scale) has already been replaced by its value.
    expect(CSS).toMatch(/^\s*--text-hero:\s*calc\(44px \* var\(--text-scale\)\);/m);
  });
```

This is the only case in the frontend that reads a computed token expecting an unresolved `var()` (`git -C $WT grep -n "getPropertyValue('--" -- 'frontend/src/**/*.spec.ts'` lists `confidence-cell.spec.ts` :80/:85, which read plain hex, and this one).

- [ ] **Step 7: Run the new spec, the token readers and the gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/resolve-token.spec.ts --include src/app/ui/chart/chart-theme.spec.ts --include src/app/ui/confidence-cell.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: `Tests  N passed`, no failures. (60 s worker timeout with no tests: re-run once.)

- [ ] **Step 8: Run the whole frontend suite once**

The jsdom document changed for every spec (no `@media` blocks any more, and every `calc(… var(--text-scale))` is pre-resolved), so prove nothing else depended on the raw file.

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false`
Expected: `Tests  N passed`, `0 failed`. A failure here means a spec read a token expecting the unflattened text: fix that spec the way Step 6 did (assert the source shape on the `tokens.css` text, keep the computed read for the value), name it in the commit body, and re-run only that spec plus `resolve-token.spec.ts`.

- [ ] **Step 9: Commit**

```bash
git -C $WT add frontend/src/app/ui/testing/resolve-token.ts frontend/src/app/ui/resolve-token.spec.ts frontend/src/test-setup.ts frontend/src/app/ui/tokens.spec.ts
git -C $WT commit -m "feat(v167): TypeScript token resolver; jsdom gets flattened token literals

resolve-token.ts ports dump_tokens.py rule for rule and is held to the same
committed fixture, so the two resolvers cannot drift. test-setup.ts injects
one :root of literals built from the fixture instead of raw tokens.css:
jsdom follows neither a nested var() nor color-mix(), and tier 2 becomes
var(--palette-name) in the palette swap. The tokens.spec hero-size case
now asserts its calc(... var(--text-scale)) shape on the source.

Narrow runs: <resolve-token + readers + GATES 'Tests  N passed'>; whole frontend: <'Tests  N passed'>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN4: Spec helpers on the resolver: `contrast.spec.ts`, `chart-palette.spec.ts` (+ new >= 3:1 on `--surface`), `chart/chart-theme.spec.ts`

**Model:** sonnet — three spec helpers rewired, one new assertion, rules unchanged

**Files:**
- Modify: `frontend/src/app/ui/contrast.spec.ts` (imports and `token()` :1-10; call sites :40, :60, :65)
- Modify: `frontend/src/app/ui/chart-palette.spec.ts` (imports, `CSS`, `token()` :1-11; call sites :49, :57, :64, :75, :81; one describe appended)
- Modify: `frontend/src/app/ui/chart/chart-theme.spec.ts` (imports :1-5, doc comment :7-21, `CSS` + `tokenValue()` :22-28; call sites in `chartPalette` describe)

**Interfaces:**
- Consumes: AN3's `resolveToken(name: string): string` from `frontend/src/app/ui/testing/resolve-token.ts`.
- Produces: no new symbols. `chart-palette.spec.ts` gains `describe('the chart series on the chart ground')` with one case per series, `ratio(resolveToken(series), resolveToken('--surface')) >= 3`. `contrast.spec.ts` keeps its `CSS` constant (the `tokens.css` text) only for the `--text-faint` "rule and divider" documentation check. AN7 relies on all three files staying green once tier 2 is `var()`.

Why (spec § 1, § 5; Amendment 1, 6): the three private helpers match only `--name: #hex;` (or raw text) in `tokens.css`. Once AN7 writes `--surface: var(--navy-900);` they throw or compare against `var(...)`. This task changes the helpers only; every threshold stays. The ">= 3:1 on `--surface`" case is new (Amendment 6: `chart-palette.spec.ts` checked no contrast before). On today's `--surface` `#131722` the six series measure 5.59 / 5.36 / 4.88 / 5.63 / 5.55 / 4.64; on AN7's `#0c1320` they measure 5.81 / 5.57 / 5.06 / 5.85 / 5.77 / 4.82, so the case passes before and after the swap.

This is a behaviour-preserving refactor of test helpers plus one assertion that already holds, so there is no red step on today's values. The red-to-green proof of these helpers is AN7, where tier 2 becomes `var()` and these files must stay green unchanged.

- [ ] **Step 1: `contrast.spec.ts` on the resolver**

In `frontend/src/app/ui/contrast.spec.ts`, replace lines 1-10:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function token(name: string): string {
  return CSS.match(new RegExp(`^\\s*${name}:\\s*(#[0-9a-fA-F]{6});`, 'm'))![1];
}
```

with:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

import { resolveToken } from './testing/resolve-token';

/**
 * The tokens.css source, read only for the `--text-faint` documentation check
 * below. Colour values come from `resolveToken()` (spec v167 § 1): tier 2 is
 * `var(--palette-name)`, which a private hex regexp would not find.
 */
const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');
```

Then replace the three call-site lines. Line 40:

```ts
        expect(ratio(token(fg), token(bg))).toBeGreaterThanOrEqual(4.5);
```

becomes:

```ts
        expect(ratio(resolveToken(fg), resolveToken(bg))).toBeGreaterThanOrEqual(4.5);
```

Line 60:

```ts
      expect(ratio(token('--accent'), token(bg))).toBeGreaterThanOrEqual(4.5);
```

becomes:

```ts
      expect(ratio(resolveToken('--accent'), resolveToken(bg))).toBeGreaterThanOrEqual(4.5);
```

Line 65:

```ts
    expect(ratio(token('--on-accent'), token('--accent-fill'))).toBeGreaterThanOrEqual(4.5);
```

becomes:

```ts
    expect(ratio(resolveToken('--on-accent'), resolveToken('--accent-fill'))).toBeGreaterThanOrEqual(4.5);
```

Check: `git -C $WT grep -n "\btoken(" -- frontend/src/app/ui/contrast.spec.ts` prints nothing.

- [ ] **Step 2: `chart-palette.spec.ts` on the resolver**

In `frontend/src/app/ui/chart-palette.spec.ts`, replace lines 1-11:

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function token(name: string): string {
  const m = CSS.match(new RegExp(`^\\s*${name}:\\s*(#[0-9a-fA-F]{6});`, 'm'));
  if (!m) throw new Error(`${name} is not defined as a hex literal`);
  return m[1];
}
```

with:

```ts
import { describe, expect, it } from 'vitest';

import { resolveToken } from './testing/resolve-token';
```

Replace the five call sites. Line 49:

```ts
    it(`defines ${name}`, () => expect(() => token(name)).not.toThrow());
```

becomes (the series stay literal hex in `tokens.css`, spec § 1, so the resolved value is a `#rrggbb`; the colour maths below parses exactly that):

```ts
    it(`defines ${name}`, () => expect(resolveToken(name)).toMatch(/^#[0-9a-f]{6}$/i));
```

Line 57: `expect(deltaE(token(name), token(valence))).toBeGreaterThan(10);` becomes `expect(deltaE(resolveToken(name), resolveToken(valence))).toBeGreaterThan(10);`

Line 64: `expect(deltaE(token(SERIES[i]), token(SERIES[i + 1]))).toBeGreaterThan(15);` becomes `expect(deltaE(resolveToken(SERIES[i]), resolveToken(SERIES[i + 1]))).toBeGreaterThan(15);`

Line 75: `const { l } = oklch(token(name));` becomes `const { l } = oklch(resolveToken(name));`

Line 81: `expect(oklch(token(name)).c).toBeGreaterThanOrEqual(0.1);` becomes `expect(oklch(resolveToken(name)).c).toBeGreaterThanOrEqual(0.1);`

Check: `git -C $WT grep -n "\btoken(\|readFileSync\|CSS" -- frontend/src/app/ui/chart-palette.spec.ts` prints nothing.

- [ ] **Step 3: Add the series-on-ground contrast case**

Append to the end of `frontend/src/app/ui/chart-palette.spec.ts`:

```ts

/** WCAG 2.1 contrast ratio of two `#rrggbb` colours. */
function ratio(fg: string, bg: string): number {
  const luminance = (hex: string) => {
    const channel = (i: number) => {
      const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
      return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };
    return 0.2126 * channel(0) + 0.7152 * channel(1) + 0.0722 * channel(2);
  };
  const [a, b] = [luminance(fg), luminance(bg)].sort((x, y) => y - x);
  return (a + 0.05) / (b + 0.05);
}

/**
 * Spec v167 § 2 and Amendment 6 (new in v167). A series is a 1px line on the
 * chart ground, `--surface` (chart-container.ts; the PNG's CHART_BG), and
 * WCAG 1.4.11 asks 3:1 of a graphical object. The floor is checked on
 * `--surface` only, deliberately: on `--surface-overlay` chart-6 measures
 * 3.94:1, and a series colour there (a tooltip swatch) carries no text.
 * A failure reopens the spec's palette table; it never lowers this number.
 */
describe('the chart series on the chart ground', () => {
  for (const name of SERIES) {
    it(`${name} clears 3:1 on --surface`, () => {
      expect(ratio(resolveToken(name), resolveToken('--surface'))).toBeGreaterThanOrEqual(3);
    });
  }
});
```

- [ ] **Step 4: `chart/chart-theme.spec.ts` on the resolver**

In `frontend/src/app/ui/chart/chart-theme.spec.ts`, replace the imports (lines 1-5):

```ts
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { chartOptions, chartPalette, tokenPx } from './chart-theme';
```

with:

```ts
import { afterEach, describe, expect, it, vi } from 'vitest';

import { resolveToken } from '../testing/resolve-token';
import { chartOptions, chartPalette, tokenPx } from './chart-theme';
```

Replace the last paragraph of the doc comment and the helper (from ` * The expected values are parsed out of \`tokens.css\` rather than written here,` through the closing `}` of `tokenValue`):

```ts
 * The expected values are parsed out of `tokens.css` rather than written here,
 * for the same reason the fallbacks were removed: a literal in this file is one
 * more copy of the palette to keep in step.
 */
const CSS = readFileSync(join(process.cwd(), 'src/styles/tokens.css'), 'utf8');

function tokenValue(name: string): string {
  const match = new RegExp(`^\\s*${name}:\\s*([^;]+);`, 'm').exec(CSS);
  if (!match) throw new Error(`tokens.css does not define ${name}`);
  return match[1].trim();
}
```

with:

```ts
 * The expected values come from `resolveToken()` rather than being written
 * here, for the same reason the fallbacks were removed: a literal in this file
 * is one more copy of the palette to keep in step. Not the raw tokens.css text
 * either: since spec v167 tier 2 reads `--pos: var(--mint-400)`, and the
 * palette must equal the literal the resolver reaches (test-setup.ts injects
 * exactly those literals).
 */
```

Then replace every `tokenValue(` with `resolveToken(` in the `chartPalette` describe (18 call sites, all of the form `expect(palette.x).toBe(tokenValue('--name'));`):

Run: `sed -i 's/tokenValue(/resolveToken(/g' $WT/frontend/src/app/ui/chart/chart-theme.spec.ts`

Check: `git -C $WT grep -n "tokenValue\|readFileSync\|CSS" -- frontend/src/app/ui/chart/chart-theme.spec.ts` prints nothing; `git -C $WT grep -c "resolveToken(" -- frontend/src/app/ui/chart/chart-theme.spec.ts` prints 18.

- [ ] **Step 5: Run the three specs, the resolver spec and the gates**

Run: `npm --prefix $WT/frontend exec -- ng test --watch=false --include src/app/ui/chart/chart-theme.spec.ts --include src/app/ui/resolve-token.spec.ts --include src/app/ui/primitives.spec.ts --include src/app/ui/elevation.spec.ts --include src/app/ui/contrast.spec.ts --include src/app/ui/chart-palette.spec.ts --include src/app/ui/tokens.spec.ts`
Expected: `Tests  N passed`, no failures; the count is 6 higher than AN3's run of the same files (the six new `clears 3:1 on --surface` cases). (60 s worker timeout with no tests: re-run once.)

- [ ] **Step 6: Commit**

```bash
git -C $WT add frontend/src/app/ui/contrast.spec.ts frontend/src/app/ui/chart-palette.spec.ts frontend/src/app/ui/chart/chart-theme.spec.ts
git -C $WT commit -m "test(v167): contrast, chart-palette and chart-theme specs read tokens through resolveToken

The three private helpers matched only literal hex (or raw text) in
tokens.css and would throw once tier 2 is var(--palette-name). Thresholds
unchanged. New: every chart series clears 3:1 on --surface (Amendment 6).

Narrow run: <'Tests  N passed'>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

# Phase 2 — Chart cache style version and supersede marks

### Task AN5: Chart cache style version: `STYLE_VERSION` in `chart_style.py`, folded into `cache._key_hash`; `STYLE_PINS` digest pin

**Model:** sonnet — one constant, one key change, two test files in one package

**Files:**
- Modify: `swingbot/core/charts/chart_style.py` (after the `THEME` dict, :55)
- Modify: `swingbot/core/charts/cache.py` (imports :10-16, `_key_hash` :22-24)
- Modify: `tests/charts/test_chart_cache.py` (two tests appended)
- Modify: `tests/charts/test_chart_theme.py` (import, `STYLE_PINS`, `_theme_digest()`, two tests; after AN2's edits to the same file)

**Interfaces:**
- Consumes: AN2's `test_chart_theme.py` (already imports `json`). From `main`: `cs.THEME`, `cache._key_hash(key_parts: dict) -> str`, `cache.cached_chart(key_parts, render_fn, cache_dir=None) -> str`, `_counting_render(calls)` in `test_chart_cache.py`.
- Produces (consumed by AN7): `chart_style.STYLE_VERSION = "v80"` (module-level `str`); `cache._key_hash` hashes `{**key_parts, "_style": STYLE_VERSION}` (signature unchanged, `from swingbot.core.charts.chart_style import STYLE_VERSION` at module top); in `test_chart_theme.py`: `_theme_digest() -> str` = `hashlib.sha256(json.dumps(cs.THEME, sort_keys=True).encode()).hexdigest()[:16]`, `STYLE_PINS: tuple[tuple[str, str], ...] = (("fb0f840658155cd0", "v80"),)` (AN7 appends `("96d64692ba7c2abf", "v167")`), tests `test_style_version_is_pinned_to_the_theme_digest` and `test_style_pins_never_reuse_a_version_or_digest`.

Why (spec § 4): the cache keys PNGs by content and lives on the `./exports` host volume for up to 7 days. Without a style component, `!stats` would serve old-palette PNGs after the AN7 deploy, and navy ones after a rollback. `_key_hash` is the single key point (`cached_chart`, `purge` and the tests all go through it), so no caller changes. `fb0f840658155cd0` is today's `THEME` digest, computed on `main` at plan time.

- [ ] **Step 1: Write the failing tests**

Append to `tests/charts/test_chart_cache.py`:

```python


def test_style_version_changes_the_key(monkeypatch):
    """Spec v167 § 4: the cache outlives a deploy on the ./exports volume, so
    the chart palette is part of every key. A THEME change (STYLE_VERSION
    bump) must miss every old entry, in both directions."""
    from swingbot.core.charts import cache

    key = {"kind": "equity_curve", "snapshot_built_at": "2026-10-16T00:00:00"}
    before = cache._key_hash(key)
    monkeypatch.setattr(cache, "STYLE_VERSION", "v-next")
    assert cache._key_hash(key) != before


def test_a_style_bump_re_renders_a_cached_chart(tmp_path, monkeypatch):
    from swingbot.core.charts import cache

    calls = []
    key = {"trade_id": "T1", "v": 3}
    first = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    monkeypatch.setattr(cache, "STYLE_VERSION", "v-next")
    second = cached_chart(key, _counting_render(calls), cache_dir=str(tmp_path))
    assert first != second
    assert len(calls) == 2
```

In `tests/charts/test_chart_theme.py`, add `import hashlib` to the standard-library imports (between `ast` and `itertools`), then insert after the `D2_SERIES = ...` line:

```python

# (sha256(THEME)[:16], STYLE_VERSION), oldest first (spec v167 § 4). When THEME
# changes, bump chart_style.STYLE_VERSION and APPEND a row; never edit a row.
# The last row must match the live pair, so a THEME edit without a version
# bump (or a bump without a THEME change) fails here.
STYLE_PINS: tuple[tuple[str, str], ...] = (
    ("fb0f840658155cd0", "v80"),
)
```

and append at the end of the file:

```python


def _theme_digest() -> str:
    return hashlib.sha256(json.dumps(cs.THEME, sort_keys=True).encode()).hexdigest()[:16]


def test_style_version_is_pinned_to_the_theme_digest():
    """The chart cache keys on STYLE_VERSION (swingbot/core/charts/cache.py), so
    a THEME change that keeps the old version would keep serving old PNGs."""
    assert (_theme_digest(), cs.STYLE_VERSION) == STYLE_PINS[-1]


def test_style_pins_never_reuse_a_version_or_digest():
    digests = [digest for digest, _ in STYLE_PINS]
    versions = [version for _, version in STYLE_PINS]
    assert len(set(digests)) == len(digests)
    assert len(set(versions)) == len(versions)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `python $WT/scripts/dev/testrun.py file tests/charts/test_chart_cache.py`
Expected: `2 failed`, the rest passed: `AttributeError: <module 'swingbot.core.charts.cache' ...> has no attribute 'STYLE_VERSION'`.

Run: `python $WT/scripts/dev/testrun.py file tests/charts/test_chart_theme.py`
Expected: `1 failed` (`test_style_version_is_pinned_to_the_theme_digest`, `AttributeError: ... 'STYLE_VERSION'`), the rest passed.

- [ ] **Step 3: Add `STYLE_VERSION` beside `THEME`**

In `swingbot/core/charts/chart_style.py`, directly after the closing `}` of `THEME` (before `CHART_BG = ...`), insert:

```python

# Folded into every chart-cache key (swingbot/core/charts/cache.py:_key_hash),
# so a THEME change, or a rollback across one, never serves a PNG drawn in the
# other palette from ./exports/chart_cache (spec v167 § 4). Bump it in the same
# commit as THEME; tests/charts/test_chart_theme.py pins the pair (STYLE_PINS).
STYLE_VERSION = "v80"
```

- [ ] **Step 4: Fold it into the cache key**

In `swingbot/core/charts/cache.py`, replace:

```python
from swingbot import config
```

with:

```python
from swingbot import config
from swingbot.core.charts.chart_style import STYLE_VERSION
```

and replace:

```python
def _key_hash(key_parts: dict) -> str:
    canonical = json.dumps(key_parts, sort_keys=True, default=str)
```

with:

```python
def _key_hash(key_parts: dict) -> str:
    # The chart palette is part of a PNG's identity: STYLE_VERSION rides in
    # every key, so a THEME change misses every old entry (spec v167 § 4).
    canonical = json.dumps({**key_parts, "_style": STYLE_VERSION}, sort_keys=True, default=str)
```

(Importing `chart_style` loads matplotlib with the Agg backend; `cache.py`'s only production caller, `swingbot/commands/stats.py`, renders charts in the same call, so nothing new is loaded in practice.)

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python $WT/scripts/dev/testrun.py file tests/charts/test_chart_cache.py`
Expected: `N passed`, `0 failed`.

Run: `python $WT/scripts/dev/testrun.py file tests/charts/test_chart_theme.py`
Expected: `N passed`, `0 failed`.

Run: `python -m radon cc -s -n C $WT/swingbot/core/charts/cache.py $WT/swingbot/core/charts/chart_style.py $WT/tests/charts/test_chart_cache.py $WT/tests/charts/test_chart_theme.py`
Expected: no output.

- [ ] **Step 6: Commit**

```bash
git -C $WT add swingbot/core/charts/chart_style.py swingbot/core/charts/cache.py tests/charts/test_chart_cache.py tests/charts/test_chart_theme.py
git -C $WT commit -m "feat(v167): chart cache keys carry STYLE_VERSION, pinned to the THEME digest

The PNG cache on ./exports outlives a deploy; without a style component a
palette change would serve old-palette charts for up to 7 days (and a
rollback the reverse). STYLE_VERSION starts at v80; STYLE_PINS fails any
THEME edit that does not append a new (digest, version) row.

Narrow runs: <test_chart_cache verdict>, <test_chart_theme verdict>

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

### Task AN6: Supersede marks in the v54 and v80 specs

**Model:** haiku — fixed doc edits at given lines

**Files:**
- Modify: `docs/superpowers/specs/implemented/2026-08-23-v54-ui-elevation-design.md` (:123, :351)
- Modify: `docs/superpowers/specs/implemented/2026-09-10-v80-terminal-foundation-design.md` (:1, :32, :71, :142, :144, :209, :279)

**Interfaces:**
- Consumes: nothing (docs only; runs in parallel with AN2..AN5).
- Produces: nine in-place marks. Nothing is deleted (Global Constraints, "Supersede, never delete"). The code-comment marks (`tokens.css`, `styles.css`, `chart_style.py`) belong to AN7, AN8 and AN9.

Below, `MARK(n)` stands for the exact text `Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §n)`; write it out in full every time. Edit each file **bottom-up** so the line numbers below stay valid; confirm each target line's text with `sed -n '<line>p' <file>` before editing it.

- [ ] **Step 1: v80, bottom-up**

In `docs/superpowers/specs/implemented/2026-09-10-v80-terminal-foundation-design.md`:

1. :279 `   - \`--radius\` and \`--radius-chip\` are 2px.` gets appended: ` *MARK(3): both tokens are deleted; four radius targets replace them.*`
2. :209 (the `sb-chip` row): replace `mono, 2px.` with `mono, 2px (*MARK(3): pills use \`--chip-radius\` 999px*).`
3. :144 `  (overlays only) is unchanged.` gets appended: ` *MARK(3): in-flow panels now cast \`--panel-shadow\` through \`.sb-panel\`; overlays keep \`--shadow-overlay\`.*`
4. :142 (the `**Radii:**` bullet) gets appended: ` *MARK(3): \`--panel-radius\` 8px, \`--control-radius\` 6px, \`--chip-radius\` 999px, \`--radius-sm\` 2px.*`
5. After :71 `## D1 — Colour tokens`, insert a blank line and: `> **MARK(2):** the Arctic Navy palette replaces these values, and tier 2 now refers to tier-1 names in \`palette.css\`. Kept for the record.`
6. :32 (the artifact URL line ending `).`) gets appended: ` *MARK(2): the partner chose a refined terminal in Arctic Navy.*`
7. After :1 (the title), insert a blank line and: `> **Superseded in part.** MARK(2) for D1's palette; MARK(3) for D3's 2px radii and the hairline-only depth rule. The canonical component set stands.`

- [ ] **Step 2: v54, bottom-up**

In `docs/superpowers/specs/implemented/2026-08-23-v54-ui-elevation-design.md`:

1. :351 (the `| G3 |` row): before the row's closing ` |`, append: ` *MARK(3): exactly two non-inset shadows, \`.sb-panel\` (\`--panel-shadow\`) and \`.elev-overlay\` (\`--shadow-overlay\`).*`
2. After :123 `## D2 — The elevation ladder, and the one-shadow law`, insert a blank line and: `> **MARK(3):** elevation has two levels now. In-flow panels cast \`--panel-shadow\` through the global \`.sb-panel\` class; out-of-flow elements cast \`--shadow-overlay\` through \`.elev-overlay\`. The ladder's surfaces stand; the one-shadow law does not.`

- [ ] **Step 3: Verify**

Run: `git -C $WT grep -c "Superseded by v167 (docs/superpowers/specs/2026-10-16-v167-arctic-navy-token-foundation-design.md §" -- docs/superpowers/specs/implemented/2026-09-10-v80-terminal-foundation-design.md docs/superpowers/specs/implemented/2026-08-23-v54-ui-elevation-design.md`
Expected: `...v80-terminal-foundation-design.md:8` and `...v54-ui-elevation-design.md:2` (v80's title note carries two marks).

Run: `git -C $WT grep -n "MARK(" -- docs/superpowers/specs/implemented/` prints nothing (every placeholder written out). `git -C $WT diff --stat` shows only insertions/changed lines in the two files, no deletions of prose.

- [ ] **Step 4: Commit**

```bash
git -C $WT add docs/superpowers/specs/implemented/2026-08-23-v54-ui-elevation-design.md docs/superpowers/specs/implemented/2026-09-10-v80-terminal-foundation-design.md
git -C $WT commit -m "docs(v167): mark v54 D2/G3 and v80 D1/D3 superseded in place

Two-level elevation, four radius targets and the Arctic Navy palette
replace the one-shadow law, the 2px radii and TradingView Blue. Marked,
not deleted.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```
