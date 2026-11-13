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


def _mirror(tmp_path):
    root = tmp_path / "market_data"
    (root / "daily").mkdir(parents=True)
    (root / "daily" / "same.csv").write_bytes(b"12345")
    (root / "daily" / "grew.csv").write_bytes(b"123")
    (root / "daily" / "gone_on_vm.csv").write_bytes(b"1")
    return root


def test_market_report_names_absent_differing_and_missing(tmp_path):
    root = _mirror(tmp_path)
    vm = {"daily/same.csv": 5, "daily/grew.csv": 9, "daily/never_pulled.csv": 4}
    lines, missing = bm.market_report(vm, root)
    assert lines == ["missing on VM: daily/gone_on_vm.csv",
                     "absent locally: daily/never_pulled.csv",
                     "size differs: daily/grew.csv"]
    assert missing == 1


def test_market_report_with_no_local_mirror_lists_everything_absent(tmp_path):
    lines, missing = bm.market_report({"a.csv": 1}, tmp_path / "nope")
    assert lines == ["absent locally: a.csv"] and missing == 0


def test_cli_report_market_prints_lines_and_the_count(tmp_path):
    root = _mirror(tmp_path)
    mpath = tmp_path / "manifest.json"
    mpath.write_text(json.dumps({"market_files": {"daily/same.csv": 5, "x.csv": 2}}), encoding="utf-8")
    out = subprocess.run([sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py"),
                          "report-market", str(mpath), str(root)],
                         capture_output=True, text=True, check=True).stdout.splitlines()
    assert "absent locally: x.csv" in out
    assert "missing on VM: daily/grew.csv" in out
    assert out[-1] == "MISSING_COUNT=2"

# ---- v221: rollback fields (v220 spec Section 2) ------------------------------
import hashlib  # noqa: E402

CONFIG_SRC = (
    "FIELDS = [\n"
    '    Field("DISCORD_TOKEN", "TOKEN", "Discord", "Bot token", type="password"),\n'
    '    Field("SCAN_INTERVAL", "scan_interval", "Scan", "Interval", default="15"),\n'
    "]\n"
)
SHA_A, SHA_B, SHA_C = "a" * 40, "b" * 40, "c" * 40


def test_config_keys_hash_covers_names_not_values_or_order():
    h = bm.config_keys_sha256(CONFIG_SRC)
    assert h == hashlib.sha256(b"DISCORD_TOKEN\nSCAN_INTERVAL").hexdigest()
    reordered = CONFIG_SRC.replace('default="15"', 'default="99"')
    lines = reordered.splitlines()
    swapped = "\n".join([lines[0], lines[2], lines[1], lines[3]]) + "\n"
    assert bm.config_keys_sha256(swapped) == h
    added = CONFIG_SRC.replace("]\n", '    Field("NEW_KEY", "new", "S", "L"),\n]\n')
    assert bm.config_keys_sha256(added) != h


def test_config_keys_hash_of_the_real_config_is_hex():
    src = (REPO / "swingbot" / "config.py").read_text(encoding="utf-8")
    h = bm.config_keys_sha256(src)
    assert len(h) == 64 and int(h, 16) >= 0


def test_features_from_log_takes_the_first_plan_id_and_skips_blanks():
    rows = bm.features_from_log([
        f"{SHA_A}\tfeat(v220): resolve targets",
        f"{SHA_B}\tmerge main into worktree",
        "",
        f"{SHA_C}\tdocs(v219): plan part 2 (v218 follow-up)\r\n",
    ])
    assert rows == [
        {"plan": "v220", "sha": SHA_A, "subject": "feat(v220): resolve targets"},
        {"plan": None, "sha": SHA_B, "subject": "merge main into worktree"},
        {"plan": "v219", "sha": SHA_C, "subject": "docs(v219): plan part 2 (v218 follow-up)"},
    ]


def _point(stable, name, sha):
    d = stable / name
    d.mkdir(parents=True)
    if sha is not None:
        (d / "manifest.json").write_text(json.dumps({"git_sha": sha}), encoding="utf-8")


def test_previous_stable_sha_picks_the_newest_point_with_a_sha(tmp_path):
    stable = tmp_path / "stable"
    _point(stable, "stable-2026-10-02", "s1")
    _point(stable, "stable-2026-10-20", "s2")
    _point(stable, "stable-2026-10-20-2", "s3")
    _point(stable, "stable-2026-10-20-10", "s4")      # -10 sorts after -2
    _point(stable, "stable-2026-10-25", None)         # no manifest: skipped
    _point(stable, "stable-2026-11-01.partial", "s5")  # never a point
    _point(stable, "notes", "s6")
    assert bm.previous_stable_sha(stable) == "s4"
    assert bm.previous_stable_sha(stable, exclude="stable-2026-10-20-10") == "s3"
    assert bm.previous_stable_sha(tmp_path / "absent") is None


def test_build_writes_rollback_fields_only_when_given(folder):
    fields = {"alembic_head": "v204_001", "bot_version": "2.17.4", "ui_version": "1.40.3",
              "config_keys_sha256": "f" * 64, "features": []}
    m = bm.build_manifest(folder, git_sha="abc", rollback=fields)
    assert {k: m[k] for k in bm.ROLLBACK_FIELDS} == fields
    assert bm.manifest_era(m) == "v220"
    old = bm.build_manifest(folder, git_sha="abc")
    assert not set(bm.ROLLBACK_FIELDS) & set(old)
    assert bm.manifest_era(old) == "pre-v220"
    assert bm.verify_folder(folder) == []


CLI = [sys.executable, str(REPO / "scripts" / "ops" / "backup_manifest.py")]


def test_cli_build_reads_the_rollback_inputs(folder, tmp_path):
    (tmp_path / "VERSION.json").write_text('{"ui": "1.40.3", "bot": "2.17.4"}', encoding="utf-8")
    (tmp_path / "config.py").write_text(CONFIG_SRC, encoding="utf-8")
    (tmp_path / "features.tsv").write_text(f"{SHA_A}\tfeat(v220): x\n", encoding="utf-8")
    out = subprocess.run(CLI + ["build", str(folder), "--alembic-head", "v204_001",
                                "--version-json", str(tmp_path / "VERSION.json"),
                                "--config-source", str(tmp_path / "config.py"),
                                "--features-log", str(tmp_path / "features.tsv")],
                         capture_output=True, text=True, check=True)
    m = json.loads(out.stdout)
    assert m["alembic_head"] == "v204_001"
    assert (m["bot_version"], m["ui_version"]) == ("2.17.4", "1.40.3")
    assert m["config_keys_sha256"] == bm.config_keys_sha256(CONFIG_SRC)
    assert m["features"] == [{"plan": "v220", "sha": SHA_A, "subject": "feat(v220): x"}]


def _verify(folder):
    return subprocess.run(CLI + ["verify", str(folder)], capture_output=True, text=True)


def test_verify_notes_a_pre_v220_stable_manifest_and_still_passes(folder):
    bm.build_manifest(folder, git_sha="abc", restic_id="r1")
    res = _verify(folder)
    assert res.returncode == 0
    assert "era: pre-v220" in res.stdout and res.stdout.rstrip().endswith("PASS")


def test_verify_prints_no_era_note_for_new_or_pull_manifests(folder):
    bm.build_manifest(folder, git_sha="abc")                  # a pull: no restic id
    assert "era:" not in _verify(folder).stdout
    fields = {k: None for k in bm.ROLLBACK_FIELDS}
    bm.build_manifest(folder, git_sha="abc", restic_id="r1", rollback=fields)
    assert "era:" not in _verify(folder).stdout


def test_cli_prev_sha_prints_the_sha_or_an_empty_line(tmp_path):
    stable = tmp_path / "stable"
    _point(stable, "stable-2026-10-20", "s2")
    got = subprocess.run(CLI + ["prev-sha", str(stable), "--exclude", "stable-2026-11-08"],
                         capture_output=True, text=True, check=True)
    assert got.stdout.strip() == "s2"
    empty = subprocess.run(CLI + ["prev-sha", str(tmp_path / "none")],
                           capture_output=True, text=True, check=True)
    assert empty.stdout.strip() == ""
