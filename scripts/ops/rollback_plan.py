#!/usr/bin/env python3
"""v220 code-only rollback planner (`/rollback`): resolve a target to one `main`
commit and its `sha-<12>` image.

Standard library only: the VM host's python3 runs this from a copy outside the
checkout (scripts/ops/rollback_code.sh), so it never imports swingbot. The
target tree is read with `git show`, never imported or run.

    python3 rollback_plan.py resolve <target> [--repo DIR] [--ref origin/main]
                                     [--deploys FILE] [--current-image IMG]
    python3 rollback_plan.py floor <sha> [--repo DIR]
    python3 rollback_plan.py candidates [--repo] [--ref] [--deploys FILE] [--stable-dir DIR] [--limit 10]

Exit codes: 0 pass, 2 refused (nothing changed).
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import NamedTuple

import rollback_checks as rc  # sibling module (scripts/ops/, or $WORK on the VM)
import rollback_migrations as rm  # sibling module

UTC = dt.timezone.utc
STABLE_RE = re.compile(r"^stable-\d{4}-\d{2}-\d{2}(-\d+)?$")
FORMS_HELP = "stable-YYYY-MM-DD[-N], <sha>, vNNN[-before|-after], bot-A.B.C, YYYY-MM-DD[THH:MM]"
PLAN_RE = re.compile(r"^v(\d+)(-before|-after)?$")
PLAN_TAG_RE = re.compile(r"\((v\d+)\)")


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
    return _read_manifest_sha(repo / "backups" / "stable" / name / "manifest.json")


def _read_manifest_sha(path: Path) -> str | None:
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


# (pattern, form, handler) -- first match wins; dates carry dashes, so they never
# reach the hex rule. V220-2 added the vNNN row.
_FORMS = (
    (STABLE_RE, "stable", _resolve_stable),
    (PLAN_RE, "plan", _resolve_plan),
    (re.compile(r"^bot-\d+\.\d+\.\d+$"), "bot", _resolve_bot),
    (re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$"), "date", _resolve_date),
    (re.compile(r"^[0-9a-fA-F]{7,40}$"), "sha", _resolve_sha),
)


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


# --- V220-6: the check report ------------------------------------------------

_CHECK_ERRORS = (subprocess.CalledProcessError, LookupError, ValueError, OSError, Refused)


@dataclass
class _Run:
    sha: str
    image: str
    repo: Path
    head: str
    env_path: Path
    allow_writer_drift: bool
    run: object
    report: dict


def _new_report() -> dict:
    return {"ok": False, "noop": False, "refusals": [], "warnings": [], "notes": [],
            "refresher": "start", "migrations": [], "hold": None}


def _check_floor(c: _Run) -> None:
    for b in floor_violations(c.sha, c.repo, INCOMPATIBLE_BOUNDARIES):
        c.report["refusals"].append(f"below the compatibility floor: {b.sha} {b.plan} {b.reason}")


def _check_migrations(c: _Run) -> None:
    for v in rm.check_migrations(c.repo, c.sha, c.head):
        c.report["migrations"].append({"revision": v.revision, "safe": v.safe,
                                       "reasons": list(v.reasons), "override": v.override})
        if not v.safe:
            c.report["refusals"].append(f"migration {v.revision} ({v.path}) is not provably additive: "
                                        + "; ".join(v.reasons))
        if v.override:
            c.report["notes"].append(f"migration {v.revision} is marked ROLLBACK_SAFE: {v.override}")


def _check_config(c: _Run) -> None:
    names = rc.env_key_names(c.env_path.read_text(encoding="utf-8"))
    refusals, warnings = rc.check_config(rc.show(c.repo, c.sha, rc.CONFIG_PATH),
                                         rc.show(c.repo, c.head, rc.CONFIG_PATH) or "", names)
    c.report["refusals"].extend(refusals)
    c.report["warnings"].extend(warnings)


def _check_compose(c: _Run) -> None:
    c.report["refusals"].extend(rc.check_compose(rc.show(c.repo, c.sha, rc.COMPOSE_PATH),
                                                 rc.show(c.repo, c.head, rc.COMPOSE_PATH) or ""))


# (label, check, needs the VM host), in spec order. V220-6b inserts vocabulary (4),
# market-data writer (6) and image tag / image / clean tree (7).
_CHECKS = (
    ("floor", _check_floor, False),
    ("migrations", _check_migrations, False),
    ("config keys", _check_config, False),
    ("compose db", _check_compose, False),
)


def _read_hold(path: Path, report: dict) -> None:
    if not path.exists():
        return
    try:
        hold = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(hold, dict):
            raise ValueError("not a JSON object")
    except (OSError, ValueError) as exc:
        report["warnings"].append(f"hold file {path} is unreadable ({exc}); a new rollback rewrites it")
        return
    report["hold"] = hold
    report["notes"].append(f"existing hold: rollback to {str(hold.get('sha', ''))[:12]} since "
                           f"{hold.get('at')}; a new rollback replaces it")


def _run_all(ctx: _Run, host: bool) -> None:
    for label, check, needs_host in _CHECKS:
        if needs_host and not host:
            ctx.report["notes"].append(f"{label}: skipped (--skip-host)")
            continue
        try:
            check(ctx)
        except _CHECK_ERRORS as exc:
            ctx.report["refusals"].append(f"{label}: cannot run: {exc}")


def run_checks(sha: str, image: str, *, repo: Path, ref: str, env_path: Path, running_sha: str,
               hold_path: Path, host: bool = True, allow_writer_drift: bool = False,
               run=subprocess.run) -> dict:
    """Every safety check for rolling back to `sha`; nothing is changed. See the CLI contract."""
    repo, report = Path(repo), _new_report()
    _read_hold(Path(hold_path), report)
    try:
        full = _on_main(_Ctx(repo, ref, Path()), sha, "target")
        head = git_out(repo, "rev-parse", f"{ref}^{{commit}}")
    except _CHECK_ERRORS as exc:
        report["refusals"].append(str(exc))
        return report
    if running_sha and _full(repo, running_sha) == full:
        report["noop"] = True
        report["notes"].append(f"target {full[:12]} is already running")
        return report
    _run_all(_Run(full, image, repo, head, Path(env_path), allow_writer_drift, run, report), host)
    report["ok"] = not report["refusals"]
    return report


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


def _cmd_floor(args: argparse.Namespace) -> int:
    violations = floor_violations(args.sha, Path(args.repo))
    for b in violations:
        print(f"below floor: {b.sha} {b.plan} {b.reason}")
    if not violations:
        print("above floor")
    return 2 if violations else 0


def _cmd_candidates(args: argparse.Namespace) -> int:
    stable_dir = Path(args.stable_dir) if args.stable_dir else Path(args.repo) / "backups" / "stable"
    rows = candidates(Path(args.repo), deploys_path=_deploys_arg(args), stable_dir=stable_dir,
                      ref=args.ref, limit=args.limit)
    print(json.dumps(rows, indent=2, sort_keys=True))
    return 0


HANDLERS = {"resolve": _cmd_resolve, "candidates": _cmd_candidates, "floor": _cmd_floor}


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
    cand = sub.add_parser("candidates", help="picker rows: recent deploys and stable points")
    _add_repo_args(cand)
    cand.add_argument("--deploys", default=None, help="default: <repo>/backups/deploys.jsonl")
    cand.add_argument("--stable-dir", default=None, help="default: <repo>/backups/stable")
    cand.add_argument("--limit", type=int, default=10)
    flo = sub.add_parser("floor", help="is <sha> at or above every incompatible boundary?")
    flo.add_argument("sha")
    flo.add_argument("--repo", default=".")
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
