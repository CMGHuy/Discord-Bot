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
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

UTC = dt.timezone.utc
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


# (pattern, form, handler) -- first match wins; dates carry dashes, so they never
# reach the hex rule. V220-2 adds the vNNN row.
_FORMS = (
    (STABLE_RE, "stable", _resolve_stable),
    (re.compile(r"^bot-\d+\.\d+\.\d+$"), "bot", _resolve_bot),
    (re.compile(r"^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?$"), "date", _resolve_date),
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
