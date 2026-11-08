# v220 — Code-only rollback, Part 1: planner (V220-1..V220-4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Spec:** [v220 — Code-only rollback](../specs/2026-11-08-v220-code-only-rollback-design.md)
**Index:** [`2026-11-08-v220-code-only-rollback_0-index.md`](2026-11-08-v220-code-only-rollback_0-index.md) — Goal, Architecture, **Global Constraints**, CLI contract, Parallelisation and the task ledger live there; every task below implicitly includes the Global Constraints.

Scope of this part: target resolution (every form in the spec's table), the compatibility floor and the picker's candidate list (`scripts/ops/rollback_plan.py`), the AST migration scanner with its tree-built revision graph and the one-time `ROLLBACK_SAFE` audit (`scripts/ops/rollback_migrations.py`), and the config-key, compose `db` block and market-data-writer checks (`scripts/ops/rollback_checks.py`).

Shared rules for these four tasks:

- All three modules are **standard library only** and import nothing from `swingbot`; tests import them with `sys.path.insert(0, str(REPO / "scripts" / "ops"))`, the `tests/scripts/test_backup_manifest.py` pattern.
- Tests that build temp git repositories skip when `git` is not on `PATH` (`shutil.which("git") is None`). Files are written with `write_bytes(text.encode("utf-8"))` so Windows never turns `\n` into `\r\n`.
- All new tests live in `tests/scripts/` (suite `tooling`); no `tests/suites.toml` change.
- Per-task verification is the narrow run only: `python scripts/dev/testrun.py file <test>`. Complexity: `python scripts/dev/complexity_gate.py` must stay green (every new function < 15).


# Phase 1 — Planner: target resolution and the floor

### Task V220-1: Target resolution: sha, stable tag, bot version, date

**Model:** sonnet — new stdlib module, behaviour fixed by the spec's form table

This task builds the module, the sha and stable-point forms and the `resolve` CLI; **V220-1b** (split for size) adds the bot-version and date forms to the same `_FORMS` table.

**Files:**
- Create: `scripts/ops/rollback_plan.py`
- Create: `tests/scripts/rollback_repo.py` (test helper, not a test module: no `test_` prefix)
- Create: `tests/scripts/test_rollback_plan_resolve.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces (final, per the ledger): `git_out(repo: Path, *args: str) -> str` (stripped stdout; `CalledProcessError` on a non-zero exit); `git_ok(repo, *args) -> bool`; `@dataclass(frozen=True) Target(sha, image, form, label)`; `class Refused(Exception)` with `.candidates: list[str]` (each `"<label> <sha12>"`); `image_for(sha: str, current_image: str) -> str`; `resolve(target: str, repo: Path, *, deploys_path: Path, current_image: str, ref: str = "origin/main") -> Target`; `main(argv=None) -> int`; `HANDLERS`; `_parser()`, `_add_repo_args(parser)`, `_print_refusal(exc)`, `_deploys_arg(args)`, `_Ctx(repo, ref, deploys_path)`, `_on_main(ctx, sha, label) -> str`, `_stable_candidates(repo, limit=5) -> list[str]`, `_FORMS` (tuple of `(pattern, form, handler)`; handlers `(text, ctx) -> (sha, label)`).
- CLI `resolve` (index CLI contract): stdout `{"sha","image","form","label"}` exit 0; stderr `REFUSE: <why>` plus one `  candidate: <label> <sha12>` per candidate, exit 2.
- Test helper `tests/scripts/rollback_repo.py`: `make_repo(tmp_path, commits: list[dict]) -> Path`, `git(repo, *args, date=None) -> str`, `sha_of(repo, rev="HEAD") -> str`, `commit_off_main(repo, subject) -> str`.

Decisions this task fixes (spec § Target resolution):
- A stable point resolves to its manifest `git_sha` when `<repo>/backups/stable/<name>/manifest.json` exists (`stable_snapshot.sh` writes `DIR="backups/stable/$NAME"`), else to its git tag; the commit must be an ancestor of `ref`.
- A hex prefix is matched against `git rev-list <ref>` only: anything off `main` is refused as "not an ancestor"; two `main` commits sharing the prefix are refused as ambiguous, both listed.
- The image is always `image_for(sha, current_image)`: the current `SWING_BOT_IMAGE` with its tag or digest replaced by `:sha-<12>` (Global Constraints).
- `main()` turns any `subprocess.CalledProcessError` (bad ref, broken repo) into `REFUSE: git failed …`, exit 2, for every subcommand later tasks add.

- [ ] **Step 1: Write the test helper**

Create `tests/scripts/rollback_repo.py`:

```python
"""Temp git repositories for the v220 rollback planner tests (V220-1, V220-1b, V220-2).

Not a test module. `make_repo` commits on `main` in order and points
`refs/remotes/origin/main` at the last commit, so code that reads `origin/main`
sees the whole fixture history.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

_IDENTITY = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}
_BASE = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)


def git(repo: Path, *args: str, date: str | None = None) -> str:
    env = {**os.environ, **_IDENTITY}
    if date:
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = date
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          encoding="utf-8", env=env, check=True)
    return done.stdout.strip()


def make_repo(tmp_path: Path, commits: list[dict]) -> Path:
    """`commits`: dicts with `subject`, optional `files` {relpath: text}, optional `tag`
    (annotated). Commit i is dated 2026-01-01T00:00Z + i hours. Returns the repo path."""
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    git(repo, "config", "commit.gpgsign", "false")
    git(repo, "config", "tag.gpgsign", "false")
    for index, spec in enumerate(commits):
        date = (_BASE + dt.timedelta(hours=index)).isoformat()
        for rel, text in spec.get("files", {}).items():
            path = repo / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
        git(repo, "add", "-A")
        git(repo, "commit", "-q", "--allow-empty", "-m", spec["subject"], date=date)
        if spec.get("tag"):
            git(repo, "tag", "-a", spec["tag"], "-m", spec["tag"], date=date)
    git(repo, "update-ref", "refs/remotes/origin/main", "HEAD")
    return repo


def sha_of(repo: Path, rev: str = "HEAD") -> str:
    return git(repo, "rev-parse", rev)


def commit_off_main(repo: Path, subject: str) -> str:
    """A commit object that exists but is not reachable from origin/main."""
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    return git(repo, "commit-tree", tree, "-p", "HEAD", "-m", subject)
```

- [ ] **Step 2: Write the failing tests**

Create `tests/scripts/test_rollback_plan_resolve.py` (V220-1b and V220-2 append to it; keep the fixture and `_resolve` as written):

```python
"""v220: rollback_plan.resolve -- every target form (V220-1, V220-1b, V220-2)."""
from __future__ import annotations

import json
import pathlib
import shutil
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_plan as rp  # noqa: E402
from tests.scripts.rollback_repo import commit_off_main, make_repo, sha_of  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

IMAGE = "ghcr.io/owner/swing-bot:sha-aaaaaaaaaaaa"


def _version(bot: str) -> dict:
    return {"VERSION.json": json.dumps({"ui": "1.0.0", "bot": bot}, indent=2) + "\n"}


def _line(ts: str, sha: str, **extra) -> str:
    return json.dumps({"ts": ts, "git_sha": sha, "bot_image": "b", "db_image": "d", **extra}) + "\n"


@pytest.fixture
def world(tmp_path):
    repo = make_repo(tmp_path, [
        {"subject": "chore: init", "files": _version("2.0.0")},
        {"subject": "feat(v200): add thing", "files": {"a.txt": "a\n"}},
        {"subject": "release(bot): 2.0.1", "files": _version("2.0.1"), "tag": "stable-2026-01-01"},
        {"subject": "docs(v210): spec", "files": {"spec.md": "s\n"}},
        {"subject": "feat(v210): build", "files": {"b.txt": "b\n"}},
        {"subject": "release(bot): 2.0.2", "files": _version("2.0.2")},
    ])
    shas = [sha_of(repo, f"HEAD~{n}") for n in range(5, -1, -1)]
    deploys = tmp_path / "deploys.jsonl"
    deploys.write_bytes((_line("2026-02-01T10:00:00Z", shas[2]) + "not json\n"
                         + _line("2026-02-03T10:00:00Z", shas[5])).encode("utf-8"))
    return {"repo": repo, "shas": shas, "deploys": deploys}


def _resolve(world, text, **kw):
    kw.setdefault("deploys_path", world["deploys"])
    kw.setdefault("current_image", IMAGE)
    return rp.resolve(text, world["repo"], **kw)


def test_full_sha_resolves_with_its_sha_image(world):
    sha = world["shas"][1]
    target = _resolve(world, sha)
    assert (target.sha, target.form) == (sha, "sha")
    assert target.image == f"ghcr.io/owner/swing-bot:sha-{sha[:12]}"


def test_seven_char_and_uppercase_prefixes_resolve(world):
    sha = world["shas"][3]
    assert _resolve(world, sha[:7]).sha == sha
    assert _resolve(world, sha[:10].upper()).sha == sha


def test_commit_off_main_is_refused(world):
    side = commit_off_main(world["repo"], "side work")
    with pytest.raises(rp.Refused, match="not an ancestor of origin/main"):
        _resolve(world, side)


def test_unknown_commit_lists_stable_candidates(world):
    with pytest.raises(rp.Refused, match="unknown commit") as exc:
        _resolve(world, "deadbeefdeadbeef")
    assert exc.value.candidates == [f"stable-2026-01-01 {world['shas'][2][:12]}"]


def test_ambiguous_prefix_is_refused_with_every_match(world, monkeypatch):
    real = rp.git_out
    first, second = "abcdef1" + "0" * 33, "abcdef1" + "1" * 33

    def fake(repo, *args):
        if args[:1] == ("rev-list",):
            return f"{first}\n{second}"
        if args[:2] == ("log", "-1"):
            return "a subject"
        return real(repo, *args)

    monkeypatch.setattr(rp, "git_out", fake)
    with pytest.raises(rp.Refused, match="ambiguous") as exc:
        _resolve(world, "abcdef1")
    assert exc.value.candidates == [f"a subject {first[:12]}", f"a subject {second[:12]}"]


def test_stable_tag_resolves_to_the_tagged_commit(world):
    target = _resolve(world, "stable-2026-01-01")
    assert (target.sha, target.form, target.label) == (world["shas"][2], "stable", "stable-2026-01-01")


def test_stable_manifest_git_sha_wins_over_the_tag(world):
    folder = world["repo"] / "backups" / "stable" / "stable-2026-01-01"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_bytes(json.dumps({"git_sha": world["shas"][1]}).encode())
    assert _resolve(world, "stable-2026-01-01").sha == world["shas"][1]


def test_stable_point_known_only_by_its_manifest_resolves(world):
    folder = world["repo"] / "backups" / "stable" / "stable-2026-01-05-2"
    folder.mkdir(parents=True)
    (folder / "manifest.json").write_bytes(json.dumps({"git_sha": world["shas"][4]}).encode())
    assert _resolve(world, "stable-2026-01-05-2").sha == world["shas"][4]


def test_unknown_stable_point_is_refused_with_candidates(world):
    with pytest.raises(rp.Refused, match="unknown stable point") as exc:
        _resolve(world, "stable-2030-01-01")
    assert exc.value.candidates[0].startswith("stable-2026-01-01 ")


def test_unknown_form_and_empty_image_are_refused(world):
    with pytest.raises(rp.Refused, match="unknown target form"):
        _resolve(world, "hello")
    with pytest.raises(rp.Refused, match="SWING_BOT_IMAGE"):
        _resolve(world, world["shas"][1], current_image="")


@pytest.mark.parametrize("current,expected", [
    ("ghcr.io/o/swing-bot:sha-111111111111", "ghcr.io/o/swing-bot:sha-0123456789ab"),
    ("ghcr.io/o/swing-bot@sha256:" + "f" * 64, "ghcr.io/o/swing-bot:sha-0123456789ab"),
    ("localhost:5000/swing-bot:latest", "localhost:5000/swing-bot:sha-0123456789ab"),
    ("swing-bot", "swing-bot:sha-0123456789ab"),
])
def test_image_for_keeps_the_repository_and_swaps_the_tag(current, expected):
    assert rp.image_for("0123456789abcdef" + "0" * 24, current) == expected


def _cli(world, *args):
    return rp.main(["resolve", *args, "--repo", str(world["repo"]), "--current-image", IMAGE])


def test_cli_resolve_prints_the_target_json(world, capsys):
    rc = _cli(world, world["shas"][5][:9], "--deploys", str(world["deploys"]))
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["sha"] == world["shas"][5]
    assert set(out) == {"sha", "image", "form", "label"}


def test_cli_refusal_exits_2_with_candidates(world, capsys):
    rc = _cli(world, "stable-2030-01-01", "--deploys", str(world["deploys"]))
    err = capsys.readouterr().err
    assert rc == 2 and err.startswith("REFUSE: unknown stable point")
    assert "  candidate: stable-2026-01-01 " in err


def test_cli_bad_ref_is_a_refusal_not_a_crash(world, capsys):
    rc = rp.main(["resolve", world["shas"][1], "--repo", str(world["repo"]),
                  "--ref", "no/such", "--current-image", IMAGE])
    assert rc == 2 and capsys.readouterr().err.startswith("REFUSE: git failed")
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_resolve.py`
Expected: collection error, `ModuleNotFoundError: No module named 'rollback_plan'`.

- [ ] **Step 4: Write the implementation**

Create `scripts/ops/rollback_plan.py`:

```python
#!/usr/bin/env python3
"""v220 code-only rollback planner (`/rollback`): resolve a target to one `main`
commit and its `sha-<12>` image.

Standard library only: the VM host's python3 runs this from a copy outside the
checkout (scripts/ops/rollback_code.sh), so it never imports swingbot. The
target tree is read with `git show`, never imported or run.

    python3 rollback_plan.py resolve <target> [--repo DIR] [--ref origin/main]
                                     [--deploys FILE] [--current-image IMG]

Exit codes: 0 pass, 2 refused (nothing changed).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

STABLE_RE = re.compile(r"^stable-\d{4}-\d{2}-\d{2}(-\d+)?$")
FORMS_HELP = "stable-YYYY-MM-DD[-N], <sha>, vNNN[-before|-after], bot-A.B.C, YYYY-MM-DD[THH:MM]"


class Refused(Exception):
    """The target cannot be used; nothing changed. `.candidates` are "<label> <sha12>"."""

    def __init__(self, message: str, candidates: list[str] | None = None):
        super().__init__(message)
        self.candidates = list(candidates or [])


@dataclass(frozen=True)
class Target:
    sha: str
    image: str
    form: str
    label: str


@dataclass(frozen=True)
class _Ctx:
    repo: Path
    ref: str
    deploys_path: Path


def git_out(repo: Path, *args: str) -> str:
    """stdout of `git -C repo <args>`, stripped; CalledProcessError on a non-zero exit."""
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True,
                          text=True, encoding="utf-8", check=True)
    return done.stdout.strip()


def git_ok(repo: Path, *args: str) -> bool:
    done = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return done.returncode == 0


def image_for(sha: str, current_image: str) -> str:
    """The current image's repository with the tag (or digest) swapped for sha-<12>."""
    if not current_image.strip():
        raise Refused("no current image to derive the registry path from (SWING_BOT_IMAGE)")
    without_digest = current_image.strip().split("@", 1)[0]
    head, _, last = without_digest.rpartition("/")
    name = last.split(":", 1)[0]
    base = f"{head}/{name}" if head else name
    return f"{base}:sha-{sha[:12]}"


def _full(repo: Path, rev: str) -> str | None:
    if not git_ok(repo, "rev-parse", "--verify", "-q", f"{rev}^{{commit}}"):
        return None
    return git_out(repo, "rev-parse", f"{rev}^{{commit}}")


def _on_main(ctx: _Ctx, sha: str, label: str) -> str:
    full = _full(ctx.repo, sha)
    if full is None:
        raise Refused(f"{label}: commit {sha[:12]} is not in this repository")
    if not git_ok(ctx.repo, "merge-base", "--is-ancestor", full, ctx.ref):
        raise Refused(f"{label} ({full[:12]}) is not an ancestor of {ctx.ref}")
    return full


def _subject(repo: Path, sha: str) -> str:
    return git_out(repo, "log", "-1", "--format=%s", sha)


def _stable_candidates(repo: Path, limit: int = 5) -> list[str]:
    tags = git_out(repo, "tag", "-l", "stable-*", "--sort=-creatordate").splitlines()
    return [f"{tag} {git_out(repo, 'rev-parse', tag + '^{commit}')[:12]}" for tag in tags[:limit]]


def _manifest_sha(repo: Path, name: str) -> str | None:
    path = repo / "backups" / "stable" / name / "manifest.json"
    try:
        sha = json.loads(path.read_text(encoding="utf-8")).get("git_sha")
    except (OSError, ValueError, AttributeError):
        return None
    return sha if isinstance(sha, str) and sha else None


def _resolve_stable(text: str, ctx: _Ctx) -> tuple[str, str]:
    sha = _manifest_sha(ctx.repo, text)
    if sha is None and git_ok(ctx.repo, "rev-parse", "--verify", "-q", f"refs/tags/{text}"):
        sha = git_out(ctx.repo, "rev-parse", f"{text}^{{commit}}")
    if sha is None:
        raise Refused(f"unknown stable point {text}", _stable_candidates(ctx.repo))
    return _on_main(ctx, sha, text), text


def _resolve_sha(text: str, ctx: _Ctx) -> tuple[str, str]:
    prefix = text.lower()
    matches = [s for s in git_out(ctx.repo, "rev-list", ctx.ref).splitlines() if s.startswith(prefix)]
    if len(matches) == 1:
        return matches[0], f"{matches[0][:12]} {_subject(ctx.repo, matches[0])[:60]}"
    if matches:
        raise Refused(f"{text} is ambiguous on {ctx.ref}",
                      [f"{_subject(ctx.repo, sha)[:60]} {sha[:12]}" for sha in matches[:10]])
    if git_ok(ctx.repo, "cat-file", "-e", f"{prefix}^{{commit}}"):
        raise Refused(f"{text} is not an ancestor of {ctx.ref}")
    raise Refused(f"unknown commit {text}", _stable_candidates(ctx.repo))


# (pattern, form, handler) -- first match wins. V220-1b inserts the bot and date
# rows before the hex rule (dates carry dashes, so they never reach it anyway).
_FORMS = (
    (STABLE_RE, "stable", _resolve_stable),
    (re.compile(r"^[0-9a-fA-F]{7,40}$"), "sha", _resolve_sha),
)


def resolve(target: str, repo: Path, *, deploys_path: Path, current_image: str,
            ref: str = "origin/main") -> Target:
    """Resolve any accepted form to one commit on `ref` plus its image; Refused otherwise."""
    text = target.strip()
    image_for("0" * 12, current_image)  # refuse early when the registry path is unknown
    ctx = _Ctx(Path(repo), ref, Path(deploys_path))
    for pattern, form, handler in _FORMS:
        if pattern.match(text):
            sha, label = handler(text, ctx)
            return Target(sha=sha, image=image_for(sha, current_image), form=form, label=label)
    raise Refused(f"unknown target form {text!r} (accepted: {FORMS_HELP})",
                  _stable_candidates(ctx.repo))


def _print_refusal(exc: Refused) -> None:
    print(f"REFUSE: {exc}", file=sys.stderr)
    for candidate in exc.candidates:
        print(f"  candidate: {candidate}", file=sys.stderr)


def _deploys_arg(args: argparse.Namespace) -> Path:
    return Path(args.deploys) if args.deploys else Path(args.repo) / "backups" / "deploys.jsonl"


def _cmd_resolve(args: argparse.Namespace) -> int:
    try:
        target = resolve(args.target, Path(args.repo), deploys_path=_deploys_arg(args),
                         current_image=args.current_image, ref=args.ref)
    except Refused as exc:
        _print_refusal(exc)
        return 2
    print(json.dumps(asdict(target), sort_keys=True))
    return 0


HANDLERS = {"resolve": _cmd_resolve}


def _add_repo_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--repo", default=".")
    parser.add_argument("--ref", default="origin/main")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="v220 code-only rollback planner")
    sub = parser.add_subparsers(dest="cmd", required=True)
    res = sub.add_parser("resolve", help="resolve a target to one main commit and its image")
    res.add_argument("target")
    _add_repo_args(res)
    res.add_argument("--deploys", default=None, help="default: <repo>/backups/deploys.jsonl")
    res.add_argument("--current-image", default=os.environ.get("SWING_BOT_IMAGE", ""))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return HANDLERS[args.cmd](args)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip().splitlines()[-1:] or [""]
        print(f"REFUSE: git failed: {' '.join(map(str, exc.cmd[3:]))}: {detail[0]}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_resolve.py`
Expected: all pass, `0 failed`.

- [ ] **Step 6: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0 (no new function at 15 or more).

- [ ] **Step 7: Commit**

```bash
git add scripts/ops/rollback_plan.py tests/scripts/rollback_repo.py tests/scripts/test_rollback_plan_resolve.py
git commit -m "feat(v220): rollback_plan resolve -- sha and stable-point targets, refusal CLI"
```

### Task V220-1b: Target resolution: bot version and date forms

**Model:** sonnet — extends one module's form table, behaviour fixed by the spec

Split from V220-1 for size (`SPLIT: V220-1 -> V220-1b`). Runs after V220-1 (same files).

**Files:**
- Modify: `scripts/ops/rollback_plan.py` (imports, new helpers above `_FORMS`, the `_FORMS` table)
- Modify: `tests/scripts/test_rollback_plan_resolve.py` (append tests)

**Interfaces:**
- Consumes (V220-1): `git_out`, `Refused`, `_Ctx`, `_on_main`, `_stable_candidates`, `_FORMS`, `rp.main`; test fixture `world`, helpers `_resolve`, `_line`, `_cli`, `IMAGE`.
- Produces: `parse_ts(text: str) -> datetime` (UTC-aware); `load_deploys(path: Path) -> list[dict]` (rows with truthy `ts` and `git_sha`, oldest first, each with a parsed `_at`; rollback/release lines included; consumed by V220-2 `candidates`); `_bot_version(repo: Path, sha: str) -> str | None` (consumed by V220-2 `candidates`); `_FORMS` rows `"bot"` and `"date"`.

Decisions (spec § Target resolution, index notes):
- `bot-A.B.C` is the oldest commit from `git log <ref> --reverse -S'"bot": "A.B.C"' -- VERSION.json` whose `git show <sha>:VERSION.json` has `bot == A.B.C` (the `-S` pickaxe also hits the commit that *removes* the string, hence the read-back).
- A bare date `YYYY-MM-DD` means the end of that UTC day (23:59:59), the deploy live at the close of that day; `YYYY-MM-DDTHH:MM` is that minute. The newest `deploys.jsonl` row at or before the moment wins, `rollback`/`release` rows included (they record what was live).
- `deploys.jsonl` is read by a local reader: the `$WORK` copy cannot import `pitr_resolve.py`. Unparsable lines, lines without `ts`/`git_sha` and unparsable timestamps are skipped, as `pitr_resolve._json_line` does.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_rollback_plan_resolve.py`:

```python
# --- V220-1b: bot version and date forms -------------------------------------


def test_bot_version_resolves_to_the_commit_that_set_it(world):
    target = _resolve(world, "bot-2.0.1")
    assert (target.sha, target.form, target.label) == (world["shas"][2], "bot", "bot-2.0.1")
    assert _resolve(world, "bot-2.0.0").sha == world["shas"][0]


def test_unknown_bot_version_is_refused_with_candidates(world):
    with pytest.raises(rp.Refused, match="sets bot 9.9.9") as exc:
        _resolve(world, "bot-9.9.9")
    assert exc.value.candidates[0].startswith("stable-2026-01-01 ")


@pytest.mark.parametrize("text,index", [
    ("2026-02-01", 2), ("2026-02-02", 2), ("2026-02-03T09:59", 2), ("2026-02-03T10:00", 5),
])
def test_date_resolves_to_the_deploy_live_then(world, text, index):
    target = _resolve(world, text)
    assert (target.sha, target.form) == (world["shas"][index], "date")
    assert target.label.startswith("deploy 2026-02-0")


def test_date_before_any_deploy_is_refused_with_the_deploys(world):
    with pytest.raises(rp.Refused, match="no deploy recorded") as exc:
        _resolve(world, "2026-01-15")
    assert exc.value.candidates == [f"deploy 2026-02-01T10:00:00Z {world['shas'][2][:12]}",
                                    f"deploy 2026-02-03T10:00:00Z {world['shas'][5][:12]}"]


def test_rollback_lines_count_as_deploys(world):
    with world["deploys"].open("ab") as fh:
        fh.write(_line("2026-02-04T00:00:00Z", world["shas"][1], kind="rollback",
                       from_sha=world["shas"][5]).encode("utf-8"))
    assert _resolve(world, "2026-02-04").sha == world["shas"][1]


def test_bad_date_is_refused(world):
    with pytest.raises(rp.Refused, match="bad date"):
        _resolve(world, "2026-13-01")


def test_missing_deploys_file_refuses_a_date(world, tmp_path):
    with pytest.raises(rp.Refused, match="no deploy recorded"):
        _resolve(world, "2026-02-02", deploys_path=tmp_path / "absent.jsonl")


def test_load_deploys_skips_junk_and_sorts(tmp_path):
    path = tmp_path / "d.jsonl"
    path.write_bytes(("not json\n" + '{"ts": "", "git_sha": "x"}\n' + '{"ts": "bad", "git_sha": "x"}\n'
                      + _line("2026-02-03T10:00:00Z", "b") + _line("2026-02-01 10:00:00", "a")
                      + '["list"]\n').encode("utf-8"))
    rows = rp.load_deploys(path)
    assert [row["git_sha"] for row in rows] == ["a", "b"]
    assert rows[0]["_at"].tzinfo is not None


def test_cli_reads_deploys_under_the_repo_by_default(world, capsys):
    (world["repo"] / "backups").mkdir()
    shutil.copy(world["deploys"], world["repo"] / "backups" / "deploys.jsonl")
    assert _cli(world, "2026-02-02") == 0
    assert json.loads(capsys.readouterr().out)["sha"] == world["shas"][2]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_resolve.py`
Expected: the V220-1b tests FAIL (`Refused: unknown target form 'bot-2.0.1'`, `AttributeError: module 'rollback_plan' has no attribute 'load_deploys'`); the V220-1 tests still pass.

- [ ] **Step 3: Write the implementation**

In `scripts/ops/rollback_plan.py`, add `import datetime as dt` to the imports (alphabetical, after `import argparse`) and, directly under the imports, `UTC = dt.timezone.utc` above `STABLE_RE`.

Insert these functions directly above the `# (pattern, form, handler)` comment:

```python
def parse_ts(text: str) -> dt.datetime:
    raw = text.strip().replace(" ", "T")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = dt.datetime.fromisoformat(raw)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _json_row(line: str) -> dict | None:
    try:
        row = json.loads(line)
        usable = isinstance(row, dict) and row.get("ts") and row.get("git_sha")
        at = parse_ts(row["ts"]) if usable else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    return {**row, "_at": at} if at else None


def load_deploys(path: Path) -> list[dict]:
    """deploys.jsonl rows with a truthy ts and git_sha, oldest first.

    rollback/release lines are included: they record what was live."""
    if not path.is_file():
        return []
    rows = [_json_row(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return sorted((row for row in rows if row), key=lambda row: row["_at"])


def _bot_version(repo: Path, sha: str) -> str | None:
    try:
        data = json.loads(git_out(repo, "show", f"{sha}:VERSION.json"))
    except (subprocess.CalledProcessError, ValueError):
        return None
    return data.get("bot") if isinstance(data, dict) else None


def _resolve_bot(text: str, ctx: _Ctx) -> tuple[str, str]:
    version = text[len("bot-"):]
    log = git_out(ctx.repo, "log", ctx.ref, "--reverse", f'-S"bot": "{version}"',
                  "--format=%H", "--", "VERSION.json")
    for sha in log.splitlines():
        if _bot_version(ctx.repo, sha) == version:
            return sha, text
    raise Refused(f"no commit on {ctx.ref} sets bot {version}", _stable_candidates(ctx.repo))


def _moment(text: str) -> dt.datetime:
    """`YYYY-MM-DDTHH:MM` is that minute (UTC); a bare date is the end of that UTC day."""
    if "T" in text:
        return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M").replace(tzinfo=UTC)
    day = dt.datetime.strptime(text, "%Y-%m-%d").replace(tzinfo=UTC)
    return day + dt.timedelta(days=1, seconds=-1)


def _resolve_date(text: str, ctx: _Ctx) -> tuple[str, str]:
    try:
        moment = _moment(text)
    except ValueError as exc:
        raise Refused(f"bad date {text}: {exc}") from None
    rows = load_deploys(ctx.deploys_path)
    live = [row for row in rows if row["_at"] <= moment]
    if not live:
        raise Refused(f"no deploy recorded at or before {text} in {ctx.deploys_path}",
                      [f"deploy {row['ts']} {row['git_sha'][:12]}" for row in rows[:5]])
    label = f"deploy {live[-1]['ts']}"
    return _on_main(ctx, live[-1]["git_sha"], label), label
```

Replace the `_FORMS` comment and table with:

```python
# (pattern, form, handler) -- first match wins; dates carry dashes, so they never
# reach the hex rule. V220-2 adds the vNNN row.
_FORMS = (
    (STABLE_RE, "stable", _resolve_stable),
    (re.compile(r"^bot-\d+\.\d+\.\d+$"), "bot", _resolve_bot),
    (re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$"), "date", _resolve_date),
    (re.compile(r"^[0-9a-fA-F]{7,40}$"), "sha", _resolve_sha),
)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_resolve.py`
Expected: all pass, `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_plan.py tests/scripts/test_rollback_plan_resolve.py
git commit -m "feat(v220): rollback_plan resolve -- bot-A.B.C and date targets from deploys.jsonl"
```

### Task V220-2: `vNNN` forms, compatibility floor, picker candidates

**Model:** sonnet — extends one module, behaviour fixed by the spec

Runs after V220-1b (same files). This task adds the `vNNN` forms, `INCOMPATIBLE_BOUNDARIES`, `floor_violations`, the floor inside `resolve` and the `floor` CLI; **V220-2b** (split for size) adds the picker `candidates`.

**Files:**
- Modify: `scripts/ops/rollback_plan.py`
- Modify: `tests/scripts/test_rollback_plan_resolve.py` (append)
- Create: `tests/scripts/test_rollback_plan_floor.py`

**Interfaces:**
- Consumes (V220-1/1b): `git_out`, `git_ok`, `_full`, `Refused`, `Target`, `_Ctx`, `_stable_candidates`, `_FORMS`, `resolve`, `HANDLERS`, `_parser`, `main`; test helpers `make_repo`, `sha_of`, fixture `world`, `_resolve`, `IMAGE`.
- Produces (final, per the ledger):
  - `class Boundary(NamedTuple): sha: str; plan: str; reason: str`.
  - `INCOMPATIBLE_BOUNDARIES: tuple[Boundary, ...]` — the three Global Constraints entries, verbatim.
  - `floor_violations(sha: str, repo: Path, boundaries=INCOMPATIBLE_BOUNDARIES) -> list[Boundary]` (a boundary sha missing from the repo counts as a violation: fail closed).
  - `resolve(...)` gains `boundaries: tuple[Boundary, ...] | None = None` (keyword, last) and refuses any target below the floor. `None` reads the module constant at call time, so tests can monkeypatch `rp.INCOMPATIBLE_BOUNDARIES`. Additive: every ledger caller keeps working.
  - `PLAN_RE`; `_FORMS` row `"plan"`; CLI `floor <sha> [--repo]`: `above floor` exit 0, or one `below floor: <sha> <plan> <reason>` line per boundary, exit 2.
  - Test fixture `chain` in `tests/scripts/test_rollback_plan_floor.py` (consumed by V220-2b).

Decisions (spec § Target resolution and Safety check 1, index notes):
- `vNNN` / `vNNN-before`: the first parent (`~1`) of the oldest commit on `<ref>` whose subject contains the literal `(vNNN)`, walking `git log <ref> --reverse --format=%H%x09%s` (all reachable commits, not `--first-parent`). That oldest match is usually the spec's `docs(vNNN)` commit; the spec defines "before" as its parent, so follow it. `(v21)` never matches `(v210)`.
- `vNNN-after`: the newest such commit.
- Ancestry is `git merge-base --is-ancestor <boundary> <target>`, never `--first-parent` (the boundaries landed via merges).

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_rollback_plan_resolve.py`:

```python
# --- V220-2: vNNN forms and the floor inside resolve --------------------------


@pytest.fixture(autouse=True)
def _no_floor(monkeypatch):
    """The real INCOMPATIBLE_BOUNDARIES shas do not exist in the temp repos."""
    monkeypatch.setattr(rp, "INCOMPATIBLE_BOUNDARIES", ())


@pytest.mark.parametrize("text,index,label", [
    ("v210", 2, "v210-before"), ("v210-before", 2, "v210-before"), ("v210-after", 4, "v210-after"),
    ("v200-before", 0, "v200-before"), ("v200-after", 1, "v200-after"),
])
def test_plan_forms_resolve_around_the_plans_commits(world, text, index, label):
    target = _resolve(world, text)
    assert (target.sha, target.form, target.label) == (world["shas"][index], "plan", label)


def test_plan_id_matches_exactly_not_by_prefix(world):
    with pytest.raises(rp.Refused, match=r"carries \(v21\)"):
        _resolve(world, "v21")


def test_unknown_plan_is_refused_with_candidates(world):
    with pytest.raises(rp.Refused, match=r"\(v999\)") as exc:
        _resolve(world, "v999-after")
    assert exc.value.candidates[0].startswith("stable-2026-01-01 ")


def test_plan_whose_first_commit_is_the_root_has_no_before(tmp_path):
    (tmp_path / "x").mkdir()
    repo = make_repo(tmp_path / "x", [{"subject": "docs(v1): spec"}, {"subject": "feat(v1): it"}])
    with pytest.raises(rp.Refused, match="has no parent"):
        rp.resolve("v1-before", repo, deploys_path=tmp_path / "none", current_image=IMAGE)
    assert rp.resolve("v1-after", repo, deploys_path=tmp_path / "none",
                      current_image=IMAGE).sha == sha_of(repo)


def test_resolve_refuses_a_target_below_the_floor(world):
    floor = (rp.Boundary(world["shas"][3], "v210", "test boundary"),)
    with pytest.raises(rp.Refused, match="below the compatibility floor") as exc:
        _resolve(world, world["shas"][1], boundaries=floor)
    assert f"{world['shas'][3]} v210 test boundary" in str(exc.value)
    assert _resolve(world, world["shas"][4], boundaries=floor).sha == world["shas"][4]
```

Create `tests/scripts/test_rollback_plan_floor.py` (V220-2b appends the candidates tests):

```python
"""v220: INCOMPATIBLE_BOUNDARIES, floor_violations (V220-2) and candidates (V220-2b)."""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import rollback_plan as rp  # noqa: E402
from tests.scripts.rollback_repo import make_repo, sha_of  # noqa: E402

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _full_history() -> bool:
    try:
        out = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--is-shallow-repository"],
                             capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return False
    return out == "false"


needs_history = pytest.mark.skipif(not _full_history(), reason="shallow or no git checkout")


def test_boundaries_are_the_spec_entries_verbatim():
    assert rp.INCOMPATIBLE_BOUNDARIES == (
        ("66e67c00", "v116", "unknown-field round-trip; older code can strip JSONB fields on re-save (merged in 14551c3c)"),
        ("2d672bab", "v184", "monitor heartbeat key (merged in b37c6e44)"),
        ("8562c35a", "v197", "durable lifecycle queue replaces the DELETE-drain consumer (migration a47f9ebc)"),
    )
    assert all(isinstance(b, rp.Boundary) for b in rp.INCOMPATIBLE_BOUNDARIES)


@needs_history
def test_every_boundary_is_an_ancestor_of_head_in_this_repo():
    assert rp.floor_violations("HEAD", REPO) == []


@pytest.fixture
def chain(tmp_path):
    repo = make_repo(tmp_path, [
        {"subject": "chore: init", "files": {"VERSION.json": '{"bot": "1.0.0"}\n'}},
        {"subject": "feat(v300): one"},
        {"subject": "release(bot): 1.0.1", "files": {"VERSION.json": '{"bot": "1.0.1"}\n'},
         "tag": "stable-2026-01-01"},
        {"subject": "feat(v301): two"},
        {"subject": "feat(v302): three", "files": {"VERSION.json": '{"bot": "1.0.2"}\n'}},
    ])
    return repo, [sha_of(repo, f"HEAD~{n}") for n in range(4, -1, -1)]


def test_floor_violations_names_each_boundary_not_yet_reached(chain):
    repo, shas = chain
    one, three = rp.Boundary(shas[1], "v300", "a"), rp.Boundary(shas[3], "v301", "b")
    assert rp.floor_violations(shas[2], repo, (one, three)) == [three]
    assert rp.floor_violations(shas[4], repo, (one, three)) == []
    assert rp.floor_violations(shas[0], repo, (one, three)) == [one, three]


def test_a_boundary_missing_from_the_repo_fails_closed(chain):
    repo, shas = chain
    ghost = rp.Boundary("0123456789ab", "v999", "absent")
    assert rp.floor_violations(shas[4], repo, (ghost,)) == [ghost]


def test_cli_floor_in_a_foreign_repo_names_all_three_boundaries(chain, capsys):
    repo, shas = chain
    assert rp.main(["floor", shas[4], "--repo", str(repo)]) == 2
    lines = capsys.readouterr().out.splitlines()
    assert [line.split()[2] for line in lines] == ["66e67c00", "2d672bab", "8562c35a"]
    assert all(line.startswith("below floor: ") for line in lines)


@needs_history
def test_cli_floor_on_head_is_above_floor(capsys):
    assert rp.main(["floor", "HEAD", "--repo", str(REPO)]) == 0
    assert capsys.readouterr().out.strip() == "above floor"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_floor.py`
Expected: FAIL, `AttributeError: module 'rollback_plan' has no attribute 'INCOMPATIBLE_BOUNDARIES'`.

- [ ] **Step 3: Write the implementation**

In `scripts/ops/rollback_plan.py`:

(a) Add `from typing import NamedTuple` after `from pathlib import Path`. In the module docstring's usage block, add the line `    python3 rollback_plan.py floor <sha> [--repo DIR]`.

(b) Directly below `FORMS_HELP`, add:

```python
PLAN_RE = re.compile(r"^v(\d+)(-before|-after)?$")


class Boundary(NamedTuple):
    sha: str
    plan: str
    reason: str


# Commits after which older code is unsafe against newer data. The floor is the
# newest entry; a target passes only when every sha here is its ancestor. A plan
# that makes old code unsafe against new data adds an entry
# (docs/claude/schema-evolution.md, the schema-change skill).
INCOMPATIBLE_BOUNDARIES: tuple[Boundary, ...] = (
    Boundary("66e67c00", "v116", "unknown-field round-trip; older code can strip JSONB fields on re-save (merged in 14551c3c)"),
    Boundary("2d672bab", "v184", "monitor heartbeat key (merged in b37c6e44)"),
    Boundary("8562c35a", "v197", "durable lifecycle queue replaces the DELETE-drain consumer (migration a47f9ebc)"),
)
```

(c) Directly above the `# (pattern, form, handler)` comment, add:

```python
def floor_violations(sha: str, repo: Path,
                     boundaries: tuple[Boundary, ...] = INCOMPATIBLE_BOUNDARIES) -> list[Boundary]:
    """Boundaries that are not ancestors of `sha`. A boundary missing from the repo counts."""
    return [b for b in boundaries
            if not git_ok(Path(repo), "merge-base", "--is-ancestor", b.sha, sha)]


def _plan_commits(ctx: _Ctx, plan: str) -> list[str]:
    tag = f"(v{plan})"
    log = git_out(ctx.repo, "log", ctx.ref, "--reverse", "--format=%H%x09%s")
    pairs = (line.partition("\t") for line in log.splitlines())
    return [sha for sha, _, subject in pairs if tag in subject]


def _resolve_plan(text: str, ctx: _Ctx) -> tuple[str, str]:
    match = PLAN_RE.match(text)
    plan, mode = match.group(1), match.group(2) or "-before"
    commits = _plan_commits(ctx, plan)
    if not commits:
        raise Refused(f"no commit on {ctx.ref} carries (v{plan})", _stable_candidates(ctx.repo))
    if mode == "-after":
        return commits[-1], f"v{plan}-after"
    parent = _full(ctx.repo, f"{commits[0]}~1")
    if parent is None:
        raise Refused(f"the first (v{plan}) commit {commits[0][:12]} has no parent")
    return parent, f"v{plan}-before"
```

(d) In `_FORMS`, add the plan row directly after the stable row, and change the comment's last sentence to "V220-2 added the vNNN row.":

```python
    (PLAN_RE, "plan", _resolve_plan),
```

(e) Replace `resolve` with:

```python
def _refuse_below_floor(repo: Path, sha: str, label: str,
                        boundaries: tuple[Boundary, ...] | None) -> None:
    bounds = INCOMPATIBLE_BOUNDARIES if boundaries is None else boundaries
    violations = floor_violations(sha, repo, bounds)
    if violations:
        named = "; ".join(f"{b.sha} {b.plan} {b.reason}" for b in violations)
        raise Refused(f"{label} ({sha[:12]}) is below the compatibility floor: {named} -- "
                      "use a whole-bot restore instead (docs/deploy/DB_RESTORE.md)")


def resolve(target: str, repo: Path, *, deploys_path: Path, current_image: str,
            ref: str = "origin/main", boundaries: tuple[Boundary, ...] | None = None) -> Target:
    """Resolve any accepted form to one commit on `ref` at or above the floor; Refused otherwise."""
    text = target.strip()
    image_for("0" * 12, current_image)  # refuse early when the registry path is unknown
    ctx = _Ctx(Path(repo), ref, Path(deploys_path))
    for pattern, form, handler in _FORMS:
        if pattern.match(text):
            sha, label = handler(text, ctx)
            _refuse_below_floor(ctx.repo, sha, label, boundaries)
            return Target(sha=sha, image=image_for(sha, current_image), form=form, label=label)
    raise Refused(f"unknown target form {text!r} (accepted: {FORMS_HELP})",
                  _stable_candidates(ctx.repo))
```

(f) Add `_cmd_floor` above `HANDLERS`, register it, and add its subparser in `_parser` directly before `return parser`:

```python
def _cmd_floor(args: argparse.Namespace) -> int:
    violations = floor_violations(args.sha, Path(args.repo))
    for b in violations:
        print(f"below floor: {b.sha} {b.plan} {b.reason}")
    if not violations:
        print("above floor")
    return 2 if violations else 0


HANDLERS = {"resolve": _cmd_resolve, "floor": _cmd_floor}
```

```python
    flo = sub.add_parser("floor", help="is <sha> at or above every incompatible boundary?")
    flo.add_argument("sha")
    flo.add_argument("--repo", default=".")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_floor.py`
Then: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_resolve.py`
Expected: both `0 failed` (the two `needs_history` tests skip only in a shallow checkout).

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_plan.py tests/scripts/test_rollback_plan_resolve.py tests/scripts/test_rollback_plan_floor.py
git commit -m "feat(v220): rollback_plan -- vNNN targets and the INCOMPATIBLE_BOUNDARIES floor"
```

### Task V220-2b: Picker candidates

**Model:** sonnet — one read-only listing function and its CLI in an existing module

Split from V220-2 for size (`SPLIT: V220-2 -> V220-2b`). Runs after V220-2 (same files).

**Files:**
- Modify: `scripts/ops/rollback_plan.py`
- Modify: `tests/scripts/test_rollback_plan_floor.py` (append)

**Interfaces:**
- Consumes: `git_out`, `git_ok`, `_full`, `STABLE_RE`, `_manifest_sha`, `load_deploys`, `_bot_version` (V220-1/1b); `Boundary`, `INCOMPATIBLE_BOUNDARIES`, `floor_violations`, `_deploys_arg`, `_add_repo_args`, `HANDLERS`, `_parser` (V220-2); test fixture `chain` (V220-2).
- Produces (final, per the ledger): `candidates(repo: Path, *, deploys_path: Path, stable_dir: Path | None, ref: str = "origin/main", limit: int = 10, boundaries: tuple[Boundary, ...] | None = None) -> list[dict]`; each row `{"label", "sha", "kind": "deploy"|"stable", "bot_version", "plans": [...], "above_floor": bool}`; CLI `candidates [--repo] [--ref] [--deploys FILE] [--stable-dir DIR] [--limit 10]` printing that list as JSON (index CLI contract). `boundaries` is an additive keyword (`None` = the module constant).

Decisions (spec § Target resolution, the no-argument picker):
- Rows: the newest `limit` distinct deploys on `<ref>` (newest first; `rollback`/`release` lines count), then the newest `limit` stable points (git tags `stable-*` plus folders under `stable_dir` holding a manifest; the manifest `git_sha` wins).
- `plans`: up to 5 distinct `(vNNN)` ids from the 15 newest subjects reachable from the row's sha, newest first.
- Rows below the floor stay in the list with `above_floor: false`; the `/rollback` skill (V220-15) shows only `above_floor` rows.

- [ ] **Step 1: Write the failing tests**

Append to `tests/scripts/test_rollback_plan_floor.py`:

```python
# --- V220-2b: picker candidates ----------------------------------------------


def _deploys(tmp_path, shas):
    path = tmp_path / "deploys.jsonl"
    lines = [{"ts": "2026-02-01T00:00:00Z", "git_sha": shas[2]},
             {"ts": "2026-02-02T00:00:00Z", "git_sha": shas[4]},
             {"ts": "2026-02-03T00:00:00Z", "git_sha": shas[4], "kind": "release"}]
    path.write_bytes("".join(json.dumps(line) + "\n" for line in lines).encode("utf-8"))
    return path


def test_candidates_list_deploys_then_stable_points(chain, tmp_path):
    repo, shas = chain
    stable_dir = tmp_path / "stable"
    (stable_dir / "stable-2026-01-05").mkdir(parents=True)
    (stable_dir / "stable-2026-01-05" / "manifest.json").write_bytes(
        json.dumps({"git_sha": shas[3]}).encode())
    (stable_dir / "not-a-point").mkdir()
    rows = rp.candidates(repo, deploys_path=_deploys(tmp_path, shas), stable_dir=stable_dir,
                         boundaries=(rp.Boundary(shas[3], "v301", "b"),))
    assert [(r["kind"], r["label"], r["sha"]) for r in rows] == [
        ("deploy", "deploy 2026-02-03T00:00:00Z", shas[4]),
        ("deploy", "deploy 2026-02-01T00:00:00Z", shas[2]),
        ("stable", "stable-2026-01-05", shas[3]),
        ("stable", "stable-2026-01-01", shas[2]),
    ]
    assert [r["above_floor"] for r in rows] == [True, False, True, False]
    assert [r["bot_version"] for r in rows] == ["1.0.2", "1.0.1", "1.0.1", "1.0.1"]
    assert rows[0]["plans"] == ["v302", "v301", "v300"]


def test_candidates_limit_and_missing_stable_dir(chain, tmp_path):
    repo, shas = chain
    rows = rp.candidates(repo, deploys_path=_deploys(tmp_path, shas), stable_dir=None,
                         limit=1, boundaries=())
    assert [(r["kind"], r["sha"]) for r in rows] == [("deploy", shas[4]), ("stable", shas[2])]


def test_candidates_skip_deploys_off_main(chain, tmp_path):
    repo, shas = chain
    path = tmp_path / "d.jsonl"
    path.write_bytes((json.dumps({"ts": "2026-02-01T00:00:00Z", "git_sha": "f" * 40}) + "\n").encode())
    assert rp.candidates(repo, deploys_path=path, stable_dir=None, boundaries=())[0]["kind"] == "stable"


def test_cli_candidates_prints_json_rows(chain, tmp_path, capsys):
    repo, shas = chain
    rc = rp.main(["candidates", "--repo", str(repo), "--deploys", str(_deploys(tmp_path, shas)),
                  "--limit", "5"])
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0 and len(rows) == 3
    assert set(rows[0]) == {"label", "sha", "kind", "bot_version", "plans", "above_floor"}
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_floor.py`
Expected: the four new tests FAIL (`AttributeError: ... no attribute 'candidates'`; the CLI test exits 2 on `invalid choice: 'candidates'`).

- [ ] **Step 3: Write the implementation**

In `scripts/ops/rollback_plan.py`:

(a) Add the usage line `    python3 rollback_plan.py candidates [--repo] [--ref] [--deploys FILE] [--stable-dir DIR] [--limit 10]` to the module docstring, and below `PLAN_RE` add:

```python
PLAN_TAG_RE = re.compile(r"\((v\d+)\)")
```

(b) Replace `_manifest_sha` with a path-based reader plus the same-named wrapper:

```python
def _read_manifest_sha(path: Path) -> str | None:
    try:
        sha = json.loads(path.read_text(encoding="utf-8")).get("git_sha")
    except (OSError, ValueError, AttributeError):
        return None
    return sha if isinstance(sha, str) and sha else None


def _manifest_sha(repo: Path, name: str) -> str | None:
    return _read_manifest_sha(repo / "backups" / "stable" / name / "manifest.json")
```

(c) Directly below `resolve`, add:

```python
def _plans_near(repo: Path, sha: str, depth: int = 15, limit: int = 5) -> list[str]:
    plans: list[str] = []
    for subject in git_out(repo, "log", f"-n{depth}", "--format=%s", sha).splitlines():
        plans.extend(p for p in PLAN_TAG_RE.findall(subject) if p not in plans)
    return plans[:limit]


def _deploy_rows(repo: Path, deploys_path: Path, ref: str, limit: int) -> list[dict]:
    rows: list[dict] = []
    for row in reversed(load_deploys(deploys_path)):
        sha = _full(repo, row["git_sha"])
        fresh = sha is not None and sha not in {r["sha"] for r in rows}
        if fresh and git_ok(repo, "merge-base", "--is-ancestor", sha, ref):
            rows.append({"label": f"deploy {row['ts']}", "sha": sha, "kind": "deploy"})
    return rows[:limit]


def _stable_points(repo: Path, stable_dir: Path | None) -> dict[str, str]:
    points = {tag: git_out(repo, "rev-parse", f"{tag}^{{commit}}")
              for tag in git_out(repo, "tag", "-l", "stable-*").splitlines()}
    folders = sorted(Path(stable_dir).iterdir()) if stable_dir and Path(stable_dir).is_dir() else []
    for folder in folders:
        sha = _read_manifest_sha(folder / "manifest.json") if STABLE_RE.match(folder.name) else None
        if sha:
            points[folder.name] = sha
    return points


def _stable_rows(repo: Path, stable_dir: Path | None, ref: str, limit: int) -> list[dict]:
    rows = []
    for name, sha in sorted(_stable_points(repo, stable_dir).items(), reverse=True):
        full = _full(repo, sha)
        if full and git_ok(repo, "merge-base", "--is-ancestor", full, ref):
            rows.append({"label": name, "sha": full, "kind": "stable"})
    return rows[:limit]


def candidates(repo: Path, *, deploys_path: Path, stable_dir: Path | None,
               ref: str = "origin/main", limit: int = 10,
               boundaries: tuple[Boundary, ...] | None = None) -> list[dict]:
    """Picker rows: newest deploys, then newest stable points, each with its floor verdict."""
    repo = Path(repo)
    bounds = INCOMPATIBLE_BOUNDARIES if boundaries is None else boundaries
    rows = _deploy_rows(repo, Path(deploys_path), ref, limit) + _stable_rows(repo, stable_dir, ref, limit)
    for row in rows:
        row["bot_version"] = _bot_version(repo, row["sha"])
        row["plans"] = _plans_near(repo, row["sha"])
        row["above_floor"] = not floor_violations(row["sha"], repo, bounds)
    return rows
```

(d) Add `_cmd_candidates` above `HANDLERS`, register it, and add its subparser in `_parser` directly before the `flo = ...` lines:

```python
def _cmd_candidates(args: argparse.Namespace) -> int:
    stable_dir = Path(args.stable_dir) if args.stable_dir else Path(args.repo) / "backups" / "stable"
    rows = candidates(Path(args.repo), deploys_path=_deploys_arg(args), stable_dir=stable_dir,
                      ref=args.ref, limit=args.limit)
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


HANDLERS = {"resolve": _cmd_resolve, "candidates": _cmd_candidates, "floor": _cmd_floor}
```

```python
    cand = sub.add_parser("candidates", help="picker rows: recent deploys and stable points")
    _add_repo_args(cand)
    cand.add_argument("--deploys", default=None, help="default: <repo>/backups/deploys.jsonl")
    cand.add_argument("--stable-dir", default=None, help="default: <repo>/backups/stable")
    cand.add_argument("--limit", type=int, default=10)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_floor.py`
Then: `python scripts/dev/testrun.py file tests/scripts/test_rollback_plan_resolve.py`
Expected: both `0 failed`.

- [ ] **Step 5: Complexity gate**

Run: `python scripts/dev/complexity_gate.py`
Expected: exit 0.

- [ ] **Step 6: Commit**

```bash
git add scripts/ops/rollback_plan.py tests/scripts/test_rollback_plan_floor.py
git commit -m "feat(v220): rollback_plan candidates -- picker rows with bot version, plans and floor verdict"
```

