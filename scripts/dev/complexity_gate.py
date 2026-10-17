"""Ratcheting cyclomatic-complexity gate (spec v149 H1).

    python scripts/dev/complexity_gate.py            # check; exit 1 on any finding
    python scripts/dev/complexity_gate.py --update   # lock in gains; never accepts a regression
    python scripts/dev/complexity_gate.py --init     # write the first baseline; refuses if one exists

Every tracked `.py` file under swingbot/, scripts/ and tests/, plus bot.py and
admin_ui.py, is measured with radon. Functions and methods scoring THRESHOLD or
more are compared with `complexity_baseline.json` next to this file, and any
difference fails, in either direction: a baseline left at an old, higher score
would let a function climb back to it unnoticed.

A function is keyed `<dotted module path>:<radon fullname>`, with no line
number, so code moving above it never touches the baseline. Closures are
measured and keyed `module:outer.inner`: radon does not fold a closure's
branches into its parent, so without that walk an inner function would be a
way around the gate.

Known limit, shared with radon's own CLI: methods of a class nested inside
another class are not listed.

Exit codes: 0 pass (or skipped: no git), 1 findings or a gate error.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
from dataclasses import dataclass

from radon.complexity import cc_visit
from radon.visitors import Function

THRESHOLD = 15
REPO = pathlib.Path(__file__).resolve().parents[2]
BASELINE = pathlib.Path(__file__).with_name("complexity_baseline.json")
SCAN_PREFIXES = ("swingbot/", "scripts/", "tests/")
SCAN_FILES = ("bot.py", "admin_ui.py")


class GateError(Exception):
    """The gate cannot give a verdict: bad source, bad baseline, key collision."""


class GitUnavailable(Exception):
    """No git or no .git (the Docker image has neither): the gate skips."""


@dataclass(frozen=True)
class Finding:
    kind: str            # "new" | "risen" | "improved" | "gone"
    key: str
    old: int | None      # baseline score; None for "new"
    new: int | None      # measured score; None for "gone"


@dataclass(frozen=True)
class _Offender:
    key: str
    score: int
    where: str           # "<path>:<line>"


def python_files(repo: pathlib.Path) -> list[str]:
    """Tracked `.py` files in scope, as sorted posix paths.

    Tracked only: concurrent sessions share this tree, and another session's
    half-written module must not fail this one's run.
    """
    if not (repo / ".git").exists():
        raise GitUnavailable(f"no .git in {repo}")
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z", "--", "*.py"], cwd=repo, check=True,
            capture_output=True, text=True, encoding="utf-8").stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise GitUnavailable(str(exc)) from exc
    paths = (pathlib.PurePosixPath(item).as_posix() for item in listing.split("\0") if item)
    return sorted(p for p in paths if p in SCAN_FILES or p.startswith(SCAN_PREFIXES))


def _module(path: str) -> str:
    return path[:-len(".py")].replace("/", ".")


def _walk(functions, parent: str = ""):
    """Yield (name, score, line) for each function and, recursively, its closures."""
    for function in functions:
        name = f"{parent}.{function.name}" if parent else function.fullname
        yield name, function.complexity, function.lineno
        yield from _walk(function.closures, name)


def _offenders(repo: pathlib.Path, path: str) -> list[_Offender]:
    try:
        source = (repo / path).read_text(encoding="utf-8")
    except FileNotFoundError:      # tracked, deleted on disk, not yet committed
        return []
    try:
        blocks = cc_visit(source)
    except (SyntaxError, ValueError) as exc:
        raise GateError(f"cannot parse {path}: {exc}") from exc
    functions = [block for block in blocks if isinstance(block, Function)]
    module = _module(path)
    return [_Offender(f"{module}:{name}", score, f"{path}:{line}")
            for name, score, line in _walk(functions) if score >= THRESHOLD]


def measure(repo: pathlib.Path, paths: list[str]) -> dict[str, int]:
    """`key -> score` for every function scoring THRESHOLD or more.

    Two offenders sharing a key is a visible failure, never a silent max.
    """
    seen: dict[str, _Offender] = {}
    for path in paths:
        for offender in _offenders(repo, path):
            first = seen.setdefault(offender.key, offender)
            if first is not offender:
                raise GateError(
                    f"key collision: {offender.key} is both {first.where} "
                    f"({first.score}) and {offender.where} ({offender.score}); "
                    "rename one of them")
    return {key: offender.score for key, offender in seen.items()}


def _valid_scores(functions) -> bool:
    return isinstance(functions, dict) and all(
        isinstance(key, str) and type(score) is int for key, score in functions.items())


def load_baseline(path: pathlib.Path) -> dict[str, int]:
    try:
        document = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GateError(f"baseline missing: {path} (create it with --init)") from exc
    except ValueError as exc:
        raise GateError(f"baseline unparseable: {path}: {exc}") from exc
    if not isinstance(document, dict) or set(document) != {"functions"} \
            or not _valid_scores(document["functions"]):
        raise GateError(
            f"baseline malformed: {path} must be exactly "
            '{"functions": {"<key>": <int>, ...}}')
    return dict(document["functions"])


def write_baseline(path: pathlib.Path, scores: dict[str, int]) -> None:
    """Sorted keys, two-space indent, trailing newline: one-line diffs."""
    text = json.dumps({"functions": dict(sorted(scores.items()))}, indent=2) + "\n"
    pathlib.Path(path).write_text(text, encoding="utf-8", newline="\n")


def _kind(old: int | None, new: int | None) -> str | None:
    if old is None:
        return "new"
    if new is None:
        return "gone"
    if new > old:
        return "risen"
    return "improved" if new < old else None


def compare(current: dict[str, int], baseline: dict[str, int]) -> list[Finding]:
    """Every difference between the scan and the baseline, sorted by key."""
    findings = []
    for key in sorted(set(current) | set(baseline)):
        old, new = baseline.get(key), current.get(key)
        kind = _kind(old, new)
        if kind:
            findings.append(Finding(kind, key, old, new))
    return findings


def shrink(baseline: dict[str, int], current: dict[str, int]) -> dict[str, int]:
    """The `--update` rule: lower improved scores, drop gone keys, add nothing."""
    return {key: min(score, current[key])
            for key, score in baseline.items() if key in current}


MAX_LINES = 20


def rename_pairs(findings: list[Finding]) -> list[tuple[str, str]]:
    """(`gone` key, `new` key) pairs with equal scores: a likely move or rename.

    One-to-one, in key order. A `gone` key with no equal-score `new` key is
    simply gone.
    """
    unclaimed = [f for f in findings if f.kind == "new"]
    pairs = []
    for gone in (f for f in findings if f.kind == "gone"):
        match = next((new for new in unclaimed if new.new == gone.old), None)
        if match:
            unclaimed.remove(match)
            pairs.append((gone.key, match.key))
    return pairs


_FORMATS = {
    "new": "new      {key}  {new}",
    "risen": "risen    {key}  {old} -> {new}",
    "improved": "improved {key}  {old} -> {new}  (run --update)",
    "gone": "gone     {key}  {old}  (run --update)",
}


def _report(findings: list[Finding]) -> None:
    print(f"VERDICT: FAIL  {len(findings)} finding(s)")
    for finding in findings[:MAX_LINES]:
        print(_FORMATS[finding.kind].format(
            key=finding.key, old=finding.old, new=finding.new))
    if len(findings) > MAX_LINES:
        print(f"... and {len(findings) - MAX_LINES} more")
    scores = {f.key: f.old for f in findings if f.kind == "gone"}
    for gone, new in rename_pairs(findings):
        print(f"hint: {gone} -> {new} looks like a move or rename "
              f"(score {scores[gone]}): hand-edit the baseline key first, "
              "then run --update")


def _scan(repo: pathlib.Path) -> dict[str, int]:
    return measure(repo, python_files(repo))


def run_check(repo: pathlib.Path, baseline_path: pathlib.Path) -> int:
    current = _scan(repo)          # first: without git the gate skips, baseline or not
    baseline = load_baseline(baseline_path)
    findings = compare(current, baseline)
    if findings:
        _report(findings)
        return 1
    print(f"VERDICT: PASS  {len(baseline)} legacy function(s) at {THRESHOLD}+, "
          "none new, risen, improved or gone")
    return 0


def run_update(repo: pathlib.Path, baseline_path: pathlib.Path) -> int:
    """Shrink the baseline. Never adds a key, never raises a score."""
    current = _scan(repo)
    baseline = load_baseline(baseline_path)
    findings = compare(current, baseline)
    if rename_pairs(findings):
        _report(findings)
        print("refused: hand-edit the baseline key first; nothing was written")
        return 1
    write_baseline(baseline_path, shrink(baseline, current))
    blocking = [f for f in findings if f.kind in ("new", "risen")]
    if blocking:
        _report(blocking)
        return 1
    locked = len(findings)
    print(f"VERDICT: PASS  baseline updated, {locked} gain(s) locked in")
    return 0


def run_init(repo: pathlib.Path, baseline_path: pathlib.Path) -> int:
    if baseline_path.exists():
        print(f"VERDICT: FAIL  {baseline_path} already exists; --init never "
              "overwrites a baseline")
        return 1
    current = _scan(repo)
    write_baseline(baseline_path, current)
    print(f"VERDICT: PASS  baseline created with {len(current)} function(s) "
          f"at {THRESHOLD}+")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--update", action="store_true",
                      help="lower improved scores and drop gone keys")
    mode.add_argument("--init", action="store_true",
                      help="write the first baseline; refuses if one exists")
    parser.add_argument("--repo", type=pathlib.Path, default=REPO)
    parser.add_argument("--baseline", type=pathlib.Path, default=BASELINE)
    args = parser.parse_args(argv)
    run = run_init if args.init else run_update if args.update else run_check
    try:
        return run(args.repo, args.baseline)
    except GitUnavailable as exc:
        print(f"VERDICT: SKIP  git unavailable, nothing measured: {exc}")
        return 0
    except GateError as exc:
        print(f"VERDICT: FAIL  {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
