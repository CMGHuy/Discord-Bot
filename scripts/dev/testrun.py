"""Quiet pytest wrapper (plan v7, Task T4) -- the entry point agents call.

Why this exists: a full-suite run costs an agent hundreds-to-thousands of
context tokens in progress dots and tracebacks, and that cost is paid on every
implementation task. This runs pytest, parks the full output in a gitignored
log, streams progress to *stderr*, and prints a 1-3 line verdict to *stdout*.
Reading a run then costs ~50 tokens.

Profiles (see docs/claude/testing-cost.md for the measurements behind them):

    python scripts/dev/testrun.py fast              # -m "not slow", serial   ~27s
    python scripts/dev/testrun.py full              # -n 4                    ~40s
    python scripts/dev/testrun.py file tests/x.py   # one path, serial         ~7s
    python scripts/dev/testrun.py lf                # --lf, serial          seconds

`fast` runs serial on purpose: measured 27.1s serial vs 27.2s at -n 4, i.e. it
is already at the fixed per-invocation overhead floor and workers only add
startup cost. `full` uses -n 4, not -n auto -- over-subscribing 12 logical
cores measured 60.0s against 40.2s.

Exit codes: 0 pass, 1 test failure, 2 could not determine the result.
"""
import argparse
import pathlib
import re
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
LOG = REPO / ".pytest-last-run.log"

WORKERS = "4"

# Neutralise pytest.ini's `addopts = -q`: under -q, pytest 9.1.1 prints no
# summary counts line at all, and a parser that sees no counts must never
# conclude "passed". -v gives per-test node IDs, which is what the progress
# tracker keys off; it is verbose on purpose because it lands in the log,
# not in anyone's context.
BASE = ["-o", "addopts=", "-v", "--tb=short", "-rf", "-p", "no:cacheprovider"]

# Matches the node id in both serial (`tests/x.py::test_y PASSED [ 5%]`) and
# xdist (`[gw2] [ 5%] PASSED tests/x.py::test_y`) verbose output.
NODE_RE = re.compile(r"(tests[/\\][\w./\\-]+\.py)::")
OUTCOME_RE = re.compile(r"\b(PASSED|FAILED|ERROR|SKIPPED|XFAIL|XPASS)\b")
FAILED_RE = re.compile(r"^(?:FAILED|ERROR)\s+(\S+)")
COUNT_RE = re.compile(r"(\d+) (passed|failed|skipped|xfailed|xpassed|error|errors|deselected)")


# Editing any of these can break a test that only runs in the slow tier, so
# `fast` transparently upgrades itself to `full` when they are dirty. Tiering
# is a speed optimisation; it must not become a way to miss a regression.
# `swingbot/admin/templates/` was here until Release B deleted it. `static/`
# stays: it is no longer page CSS, but `static/tokens.css` is still the source
# `core/charts/chart_style.THEME` mirrors, and tests/test_chart_theme.py pins
# the two together -- so editing it can still break a render-tier test.
ESCALATE_PREFIXES = (
    "swingbot/core/charts/",
    "swingbot/admin/static/",
)


def changed_paths() -> list[str] | None:
    """Working-tree + staged paths vs HEAD. None if git can't answer."""
    try:
        out = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"], cwd=REPO,
            capture_output=True, text=True, timeout=15,
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"], cwd=REPO,
            capture_output=True, text=True, timeout=15,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    paths = out.stdout.splitlines() + untracked.stdout.splitlines()
    return [p.strip().replace("\\", "/") for p in paths if p.strip()]


def should_escalate() -> tuple[bool, str]:
    paths = changed_paths()
    if paths is None:
        # Fail safe, not fast: if we cannot tell what changed, run everything.
        return True, "git unavailable"
    hits = [p for p in paths if p.startswith(ESCALATE_PREFIXES)]
    if hits:
        return True, f"{hits[0]}{'' if len(hits) == 1 else f' (+{len(hits) - 1} more)'} touched"
    return False, ""


def build_args(profile: str, target: str | None) -> list[str]:
    if profile == "fast":
        return BASE + ["-m", "not slow", "tests/"]
    if profile == "full":
        return BASE + ["-n", WORKERS, "tests/"]
    if profile == "lf":
        return BASE + ["--lf", "tests/"]
    if profile == "file":
        if not target:
            sys.exit("testrun.py file <path>: missing path")
        return BASE + [target]
    sys.exit(f"unknown profile: {profile}")


def run(pytest_args: list[str]) -> tuple[dict[str, int], list[str], float, int]:
    """Stream pytest, log everything, emit per-file progress on stderr."""
    cmd = [sys.executable, "-m", "pytest", *pytest_args]
    started = time.time()
    counts: dict[str, int] = {}
    failed: list[str] = []
    seen: set[str] = set()

    # Collection plus xdist worker startup is ~30s of silence before the first
    # test result. Announce immediately so a watcher can tell "starting up"
    # from "hung" -- CLAUDE.md's rule is that a long run must never give zero
    # signal.
    print(f"  running: {' '.join(pytest_args)}", file=sys.stderr, flush=True)
    print("  collecting (no per-file output until the first test finishes)...",
          file=sys.stderr, flush=True)

    with LOG.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"$ {' '.join(cmd)}\n\n")
        proc = subprocess.Popen(
            cmd, cwd=REPO, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace", bufsize=1,
        )
        for line in proc.stdout:
            log.write(line)

            node = NODE_RE.search(line)
            if node and OUTCOME_RE.search(line):
                path = node.group(1).replace("\\", "/")
                if path not in seen:
                    seen.add(path)
                    # stderr, so progress never pollutes the read path
                    print(f"  [{len(seen):3d}] {path}", file=sys.stderr, flush=True)

            hit = FAILED_RE.match(line)
            if hit and hit.group(1) not in failed:
                failed.append(hit.group(1))

            if " in " in line and ("passed" in line or "failed" in line or "error" in line):
                found = COUNT_RE.findall(line)
                if found:
                    counts = {k: int(n) for n, k in found}

        rc = proc.wait()
    return counts, failed, time.time() - started, rc


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("profile", choices=["fast", "full", "file", "lf"])
    ap.add_argument("target", nargs="?")
    ap.add_argument("--no-escalate", action="store_true",
                    help="keep `fast` narrow even if chart/template files changed")
    args = ap.parse_args()

    profile = args.profile
    if profile == "fast" and not args.no_escalate:
        escalate, why = should_escalate()
        if escalate:
            print(f"NOTE: {why} -> escalating to full tier")
            profile = "full"

    counts, failed, elapsed, rc = run(build_args(profile, args.target))

    # No parseable counts means we do not know what happened. Never optimistic.
    if not counts:
        print(f"VERDICT: UNKNOWN (could not parse pytest output)  in {elapsed:.1f}s")
        print(f"  pytest exit code {rc}; full output: {LOG}")
        return 2

    order = ["passed", "failed", "error", "errors", "skipped", "xfailed", "xpassed", "deselected"]
    summary = ", ".join(f"{counts[k]} {k}" for k in order if counts.get(k))
    bad = counts.get("failed", 0) + counts.get("error", 0) + counts.get("errors", 0)

    if bad == 0 and rc == 0:
        print(f"VERDICT: PASS  {summary}  in {elapsed:.1f}s")
        return 0

    print(f"VERDICT: FAIL  {summary}  in {elapsed:.1f}s")
    for node in failed[:10]:
        print(f"  {node}")
    if len(failed) > 10:
        print(f"  ... and {len(failed) - 10} more")
    print(f"  full output: {LOG}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
