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
