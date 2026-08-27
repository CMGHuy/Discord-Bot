"""Verify that a refactor moved functions without editing their bodies.

Used by the v61 decomposition plans (docs/superpowers/plans/). The move
invariant is that a relocated function's body is byte-identical; this
compares ASTs so that import-block and formatting differences around the
move are ignored while any change inside a body is reported.
"""
import argparse
import ast
import subprocess
import sys


def _bodies(source: str) -> dict:
    tree = ast.parse(source)
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out[node.name] = ast.dump(ast.Module(body=node.body, type_ignores=[]))
    return out


def check_move_purity(old_source: str, new_source: str, symbols: list) -> list:
    """Return the names in `symbols` whose body differs between the two sources."""
    old, new = _bodies(old_source), _bodies(new_source)
    differing = []
    for name in symbols:
        if name not in old or name not in new or old[name] != new[name]:
            differing.append(name)
    return differing


def _read_ref(spec: str) -> str:
    if ":" in spec:
        return subprocess.run(["git", "show", spec], capture_output=True,
                              text=True, check=True).stdout
    with open(spec, encoding="utf-8") as fh:
        return fh.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", help="git ref:path, e.g. HEAD:swingbot/commands/scanning.py")
    ap.add_argument("new", help="path to the new file on disk")
    ap.add_argument("symbols", nargs="+")
    args = ap.parse_args()

    bad = check_move_purity(_read_ref(args.old), _read_ref(args.new), args.symbols)
    if bad:
        print("MOVE NOT PURE -- these bodies differ or are missing:")
        for name in bad:
            print(f"  - {name}")
        return 1
    print(f"OK -- {len(args.symbols)} symbol(s) moved unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
