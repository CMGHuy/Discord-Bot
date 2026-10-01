"""backup_manifest.py (v120 §3): the verifier is what decides whether an off-VM
copy counts, so every way a copy can be wrong must fail it."""
import gzip
import json
import pathlib
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts" / "ops"))
import backup_manifest as bm  # noqa: E402


@pytest.fixture
def folder(tmp_path):
    d = tmp_path / "2026-10-01T18-04Z"
    d.mkdir()
    with gzip.open(d / "db.sql.gz", "wb") as fh:
        fh.write(b"-- dump\n" * 100)
    (d / "env").write_text("TOKEN=x\n")
    (d / "deploys.jsonl").write_text('{"git_sha": "abc"}\n')
    return d


def test_round_trip_passes(folder):
    m = bm.build_manifest(folder, git_sha="abc", vm_epoch=1759341840,
                          deploy={"bot_image": "b", "db_image": "d"})
    assert m["schema"] == 1 and m["bot_image"] == "b"
    assert set(m["files"]) == {"db.sql.gz", "env", "deploys.jsonl"}
    assert bm.verify_folder(folder) == []


def test_flipped_byte_fails(folder):
    bm.build_manifest(folder)
    p = folder / "env"
    p.write_bytes(b"TOKEN=y\n")
    assert any("sha256" in e for e in bm.verify_folder(folder))


def test_missing_and_unlisted_files_fail(folder):
    bm.build_manifest(folder)
    (folder / "env").unlink()
    (folder / "stray").write_text("x")
    problems = bm.verify_folder(folder)
    assert any("missing" in e and "env" in e for e in problems)
    assert any("unlisted" in e and "stray" in e for e in problems)


def test_truncated_gzip_fails_even_with_matching_hash(folder):
    raw = (folder / "db.sql.gz").read_bytes()
    (folder / "db.sql.gz").write_bytes(raw[: len(raw) // 2])
    bm.build_manifest(folder)                      # hash matches the truncated file
    assert any("gzip" in e for e in bm.verify_folder(folder))


def test_no_manifest_fails(folder):
    assert bm.verify_folder(folder)


def _pull(root, name):
    p = root / "pulls" / name
    p.mkdir(parents=True)
    return p


def test_prune_keeps_newest_good_and_drops_older_failed(tmp_path):
    for i in range(12):
        _pull(tmp_path, f"2026-10-{i + 1:02d}T00-00Z")
    _pull(tmp_path, "2026-09-30T00-00Z.FAILED")
    _pull(tmp_path, "2026-10-13T00-00Z.FAILED")    # newer than newest good: kept
    (tmp_path / "stable" / "stable-2026-09-01").mkdir(parents=True)
    (tmp_path / "market_data").mkdir()
    removed = {p.name for p in bm.prune_pulls(tmp_path, keep=10)}
    assert removed == {"2026-10-01T00-00Z", "2026-10-02T00-00Z", "2026-09-30T00-00Z.FAILED"}
    assert (tmp_path / "stable" / "stable-2026-09-01").exists()
    assert (tmp_path / "market_data").exists()
    assert (tmp_path / "pulls" / "2026-10-13T00-00Z.FAILED").exists()


@pytest.mark.parametrize("existing,expected", [
    (set(), "stable-2026-10-01"),
    ({"stable-2026-10-01"}, "stable-2026-10-01-2"),
    ({"stable-2026-10-01", "stable-2026-10-01-2"}, "stable-2026-10-01-3"),
    ({"stable-2026-09-17"}, "stable-2026-10-01"),
])
def test_next_stable_name(existing, expected):
    assert bm.next_stable_name("2026-10-01", existing) == expected


def test_cli_verify_exit_codes(folder):
    bm.build_manifest(folder)
    cli = [sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py")]
    ok = subprocess.run(cli + ["verify", str(folder)], capture_output=True, text=True)
    assert ok.returncode == 0 and "PASS" in ok.stdout
    (folder / "env").write_text("changed")
    bad = subprocess.run(cli + ["verify", str(folder)], capture_output=True, text=True)
    assert bad.returncode == 1


def test_cli_build_reads_market_files(folder, tmp_path):
    listing = tmp_path / "mf.tsv"
    listing.write_text("120\tdaily/AAPL.csv\n7\tintraday/AAPL/2026-10-01.csv\n")
    cli = [sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py")]
    out = subprocess.run(cli + ["build", str(folder), "--market-files", str(listing)],
                         capture_output=True, text=True, check=True)
    assert json.loads(out.stdout)["market_files"]["daily/AAPL.csv"] == 120


DUMP = (
    "SET statement_timeout = 0;\nSET client_encoding = 'UTF8';\n"
    "CREATE TABLE public.trades (id integer);\n"
    "COPY public.trades (id, sym) FROM stdin;\n1\tAAPL\n2\tMSFT\n3\tNVDA\n\\.\n\n"
    "COPY public.empty_t (id) FROM stdin;\n\\.\n\n"
    'COPY public."Odd Name" (a) FROM stdin;\nx\n\\.\n\n'
    "COPY audit.events (id, note) FROM stdin;\n1\tfirst\n2\tsecond\n\\.\n\n"
    # COPY text escapes a data backslash as two, so a value line may hold "\\\\."
    "COPY public.notes (txt) FROM stdin;\nab\\\\.cd\n\\\\.\nlast\n\\.\n"
)


@pytest.fixture
def dump(tmp_path):
    p = tmp_path / "db.sql.gz"
    with gzip.open(p, "wb") as fh:
        fh.write(DUMP.encode())
    return p


def test_count_dump_counts_rows_per_copy_block(dump):
    assert bm.count_dump(dump) == {
        "audit.events": 2, "public.Odd Name": 1, "public.empty_t": 0,
        "public.notes": 3, "public.trades": 3}


def test_cli_count_dump_prints_sorted_json(dump):
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py"),
                          "count-dump", str(dump)], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == json.dumps(
        {"audit.events": 2, "public.Odd Name": 1, "public.empty_t": 0,
         "public.notes": 3, "public.trades": 3}, sort_keys=True)




def test_size_only_mismatch_is_reported(folder):
    bm.build_manifest(folder)
    mpath = folder / "manifest.json"
    data = json.loads(mpath.read_text(encoding="utf-8"))
    data["files"]["env"]["bytes"] += 1               # the hash still matches
    mpath.write_text(json.dumps(data), encoding="utf-8")
    assert bm.verify_folder(folder) == ["size mismatch: env"]


@pytest.mark.parametrize("keep", [0, -1, -5])
def test_prune_rejects_keep_below_one(tmp_path, keep):
    _pull(tmp_path, "2026-10-01T00-00Z")
    with pytest.raises(ValueError):
        bm.prune_pulls(tmp_path, keep=keep)
    assert (tmp_path / "pulls" / "2026-10-01T00-00Z").exists()


@pytest.mark.parametrize("keep", ["0", "-3"])
def test_cli_prune_rejects_keep_below_one(tmp_path, keep):
    _pull(tmp_path, "2026-10-01T00-00Z")
    r = subprocess.run([sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py"),
                        "prune", str(tmp_path), "--keep", keep], capture_output=True, text=True)
    assert r.returncode == 2
    assert (tmp_path / "pulls" / "2026-10-01T00-00Z").exists()


def test_prune_refuses_pulls_resolving_outside_backups(tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    backups = tmp_path / "backups"
    backups.mkdir()
    try:
        (backups / "pulls").symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation not permitted here")
    with pytest.raises(ValueError):
        bm.prune_pulls(backups, keep=10)


def test_this_module_compiles_without_warnings():
    import ast
    import warnings
    src = (REPO / "tests" / "scripts" / "test_backup_manifest.py").read_text(encoding="utf-8")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        ast.parse(src)
