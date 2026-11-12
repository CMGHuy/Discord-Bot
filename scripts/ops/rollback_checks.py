#!/usr/bin/env python3
"""v220 safety checks 3, 4, 5 and 6 (config keys, open-trade vocabulary, compose db block, market-data writer).

Reads the target tree with `git show <sha>:<path>` and `ast`; never imports or runs
a target file. `.env` is read for key NAMES only -- no value ever reaches output.
Standard library only: the VM host's python3 runs this from a copy.
"""
from __future__ import annotations

import ast
import difflib
import re
import subprocess
from pathlib import Path

CRITICAL_KEYS = ("DISCORD_TOKEN", "POSTGRES_PASSWORD", "DATABASE_URL")
CONFIG_PATH = "swingbot/config.py"
COMPOSE_PATH = "docker-compose.yml"
MARKET_DATA_WRITER_PATHS: tuple[str, ...] = (
    "swingbot/refresher/",
    "swingbot/core/marketdata/data_store.py",   # save_to_disk: market_data/<interval>/<TICKER>.csv
    "swingbot/core/marketdata/data_refresh.py",  # refresh_symbol
)
_ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")
_DB_LINE = re.compile(r"^(\s+)db:\s*(#.*)?$")


def show(repo: Path, sha: str, path: str) -> str | None:
    """`git show <sha>:<path>` as text; None when the path is absent at that commit."""
    proc = subprocess.run(["git", "-C", str(repo), "show", f"{sha}:{path}"], capture_output=True,
                          text=True, encoding="utf-8")
    return proc.stdout if proc.returncode == 0 else None


def _is_field_call(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not node.args:
        return False
    func = node.func
    name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
    first = node.args[0]
    return name == "Field" and isinstance(first, ast.Constant) and isinstance(first.value, str)


def declared_config_keys(source: str) -> list[str]:
    """Every `.env` key a config.py declares: the first positional string of each Field(...)."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(f"unparsable: {exc.msg} (line {exc.lineno})") from None
    keys = {node.args[0].value for node in ast.walk(tree) if _is_field_call(node)}
    if not keys:
        raise ValueError("no Field(...) declarations found")
    return sorted(keys)


def env_key_names(env_text: str) -> set[str]:
    """Key names of a .env file; values are matched over and never kept."""
    names = set()
    for line in env_text.splitlines():
        match = _ENV_KEY.match(line)
        if match:
            names.add(match.group(1))
    return names


def _keys_or_refusal(source: str | None, who: str) -> tuple[list[str] | None, str | None]:
    if not source:
        return None, f"{who} {CONFIG_PATH} is missing or empty"
    try:
        return declared_config_keys(source), None
    except ValueError as exc:
        return None, f"{who} {CONFIG_PATH} cannot be read: {exc}"


def check_config(target_config: str | None, head_config: str,
                 env_names: set[str]) -> tuple[list[str], list[str]]:
    """Check 3: (refusals, warnings). Names only; .env values never enter the result."""
    target, refusal = _keys_or_refusal(target_config, "target")
    if refusal:
        return [refusal], []
    head, refusal = _keys_or_refusal(head_config, "HEAD")
    if refusal:
        return [refusal], []
    refusals = [f"critical key {key} is missing from .env" for key in CRITICAL_KEYS if key not in env_names]
    warnings = [f"{key}: declared by the target, no longer declared at HEAD and absent from .env "
                "(the old code runs on its default)"
                for key in target if key not in head and key not in env_names and key not in CRITICAL_KEYS]
    return refusals, warnings


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _is_content(line: str) -> bool:
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#")


def _services_children(lines: list[str]) -> list[int]:
    """Indexes of the content lines inside the top-level `services:` mapping."""
    inside, found = False, []
    for i, line in enumerate(lines):
        if _is_content(line) and _indent(line) == 0:
            inside = line.rstrip() == "services:"
            continue
        if inside and _is_content(line):
            found.append(i)
    return found


def compose_db_block(compose_text: str) -> str:
    """The `db` service block, comment-only and blank lines dropped, trailing space stripped."""
    lines = compose_text.splitlines()
    children = _services_children(lines)
    child_indent = _indent(lines[children[0]]) if children else 0
    start = next((i for i in children if _DB_LINE.match(lines[i]) and _indent(lines[i]) == child_indent), None)
    if start is None:
        raise ValueError("no db service under services:")
    block = [lines[start].rstrip()]
    for line in lines[start + 1:]:
        if _is_content(line) and _indent(line) <= child_indent:
            break
        if _is_content(line):
            block.append(line.rstrip())
    return "\n".join(block)


def _block_or_refusal(text: str | None, who: str) -> tuple[str | None, str | None]:
    if not text:
        return None, f"{who} {COMPOSE_PATH} is missing or empty"
    try:
        return compose_db_block(text), None
    except ValueError as exc:
        return None, f"{who} {COMPOSE_PATH} cannot be read: {exc}"


def check_compose(target_text: str | None, head_text: str) -> list[str]:
    """Check 5: refuse unless the target's db service block equals HEAD's."""
    target, refusal = _block_or_refusal(target_text, "target")
    if refusal:
        return [refusal]
    head, refusal = _block_or_refusal(head_text, "HEAD")
    if refusal:
        return [refusal]
    if target == head:
        return []
    diff = [d for d in difflib.unified_diff(head.splitlines(), target.splitlines(), lineterm="", n=0)
            if d[:1] in "+-" and not d.startswith(("+++", "---"))]
    return ["compose db service differs between target and HEAD (Compose would recreate Postgres): "
            + "; ".join(d.strip() for d in diff[:4])]


def changed_writer_paths(repo: Path, target_sha: str, head_sha: str,
                         paths: tuple[str, ...] = MARKET_DATA_WRITER_PATHS) -> list[str]:
    """Check 6: files under the market-data writer paths that differ between target and HEAD."""
    out = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", target_sha, head_sha, "--", *paths],
                         capture_output=True, text=True, encoding="utf-8", check=True).stdout
    return sorted(line for line in out.splitlines() if line)


# --- Check 4: open-trade vocabulary (V220-5) ---------------------------------

VOCAB_FIELDS = ("status", "strategy", "source", "entry_type", "ledger", "lifecycle_kind")
_OPEN_PLANS = "status IN ('PENDING', 'ACTIVE', 'PARTIAL')"
# One row per (field, value) stored on an open trade. `plans` promotes status and
# strategy to columns; source, entry_type and ledger live in its doc. The v197
# lifecycle queue is manual_close_notify; an undelivered event's kind is doc->>'kind'.
# UNION removes duplicates; NULLs print as empty values and are dropped by the reader.
VOCAB_SQL = f"""
SELECT 'status', status FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'strategy', strategy FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'source', doc->>'source' FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'entry_type', doc->>'entry_type' FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'ledger', doc->>'ledger' FROM plans WHERE {_OPEN_PLANS}
UNION SELECT 'strategy', strategy FROM journal_entries WHERE closed_at IS NULL
UNION SELECT 'lifecycle_kind', doc->>'kind' FROM manual_close_notify WHERE delivered_at IS NULL
ORDER BY 1, 2
"""
# psql inside the db container, every transaction read-only, bare tab-separated rows.
PSQL: tuple[str, ...] = (
    "docker", "compose", "exec", "-T", "-e", "PGOPTIONS=-c default_transaction_read_only=on", "db",
    "psql", "-X", "-U", "swingbot", "-d", "swingbot", "-v", "ON_ERROR_STOP=1", "-A", "-t", "-F", "\t", "-c",
)


def psql_lines(sql: str, *, app_dir: Path, run=subprocess.run) -> list[str]:
    """Non-blank output rows of one read-only query; CalledProcessError when it fails."""
    done = run([*PSQL, sql], cwd=str(app_dir), capture_output=True, text=True,
               encoding="utf-8", check=True)
    return [line for line in done.stdout.splitlines() if line.strip()]


def vocab_from_db(*, app_dir: Path, run=subprocess.run) -> dict[str, set[str]]:
    """field -> distinct stored values of the open trades (every VOCAB_FIELDS key present)."""
    values: dict[str, set[str]] = {field: set() for field in VOCAB_FIELDS}
    for line in psql_lines(VOCAB_SQL, app_dir=app_dir, run=run):
        field, _, value = line.partition("\t")
        if field in values and value.strip():
            values[field].add(value)
    return values


def _literal_in_tree(repo: Path, sha: str, value: str) -> bool:
    """True when "value" or 'value' occurs in a file under swingbot/ at `sha`."""
    proc = subprocess.run(["git", "-C", str(repo), "grep", "-q", "-F", "-e", f'"{value}"',
                           "-e", f"'{value}'", sha, "--", "swingbot"],
                          capture_output=True, text=True, encoding="utf-8")
    if proc.returncode in (0, 1):
        return proc.returncode == 0
    raise subprocess.CalledProcessError(proc.returncode, proc.args, proc.stdout, proc.stderr)


def missing_vocabulary(repo: Path, sha: str, values: dict[str, set[str]]) -> list[str]:
    """Check 4: every stored value the target tree does not know, as "<field>=<value>"."""
    return [f"{field}={value}"
            for field in sorted(values) for value in sorted(values[field])
            if not _literal_in_tree(Path(repo), sha, value)]
