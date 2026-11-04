"""SessionStart hook: give every worktree the main checkout's permissions.

`.claude/settings.local.json` is git-ignored, so a fresh worktree starts with
none of the allow rules the partner granted on the main checkout. This copies
the file when missing and otherwise adds any allow/deny/ask rule main has and
the worktree lacks (never removes a worktree-only rule).
Contract: never fails a session start; always exits 0.
"""
import json
import pathlib
import subprocess

REL = pathlib.Path(".claude/settings.local.json")
LISTS = ("allow", "deny", "ask")


def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _main_checkout():
    common = pathlib.Path(_git("rev-parse", "--path-format=absolute", "--git-common-dir"))
    return common.parent


def _merge(src: dict, dst: dict) -> bool:
    changed = False
    sperm, dperm = src.get("permissions", {}), dst.setdefault("permissions", {})
    for key in LISTS:
        have = dperm.setdefault(key, []) if sperm.get(key) else dperm.get(key, [])
        for rule in sperm.get(key, []):
            if rule not in have:
                have.append(rule)
                changed = True
    return changed


def sync(here: pathlib.Path, main: pathlib.Path) -> str:
    if here.resolve() == main.resolve() or not (main / REL).is_file():
        return "nothing to do"
    target = here / REL
    if not target.is_file():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((main / REL).read_bytes())
        return "copied settings.local.json from the main checkout"
    src = json.loads((main / REL).read_text(encoding="utf-8"))
    dst = json.loads(target.read_text(encoding="utf-8"))
    if _merge(src, dst):
        target.write_text(json.dumps(dst, indent=2) + "\n", encoding="utf-8")
        return "added missing permission rules from the main checkout"
    return "already in step"


def main():
    try:
        here = pathlib.Path(_git("rev-parse", "--show-toplevel"))
        msg = sync(here, _main_checkout())
        if msg != "nothing to do":
            print(f"worktree permissions: {msg}")
    except Exception as exc:  # a hook must never block a session
        print(f"worktree permissions sync skipped: {exc}")


if __name__ == "__main__":
    main()
