"""NG12 — /api/v1/jobs and /api/v1/analytics/tuning/proposals.

The security-relevant tests here are the traversal ones. `job_id` and a
proposal `filename` both flow from client input into a filesystem path, and
Flask's URL converter rejects '/' but not '\'. On Windows os.path.join
treats a backslash as a separator and a drive-letter prefix as an
absolute-path override that discards the directory entirely -- so without
the allow-list regexes the delete route is an arbitrary-file-delete
primitive. pages.py carries that guard; these confirm v1 kept it.
"""
import json
import os

import pytest

from tests.admin.api_v1_contract import assert_error, assert_shape

_LOGIN = {"username": "admin", "password": "admin"}


@pytest.fixture
def logged_in(client):
    client.post("/api/v1/session", json=_LOGIN)
    return client


@pytest.fixture
def proposals_dir(admin_app, tmp_path):
    d = tmp_path / "tuning_proposals"
    d.mkdir(exist_ok=True)
    return d


def test_jobs_require_auth(client):
    assert_error(client.get("/api/v1/jobs"), "auth", 401)


def test_list_jobs_is_empty_initially(logged_in):
    assert_shape(logged_in.get("/api/v1/jobs").get_json(), {"jobs": list})


def test_unknown_job_is_404(logged_in):
    assert_error(logged_in.get("/api/v1/jobs/nosuchjob"), "not_found", 404)


@pytest.mark.parametrize("bad", ["..\secrets", "a.b", "a;b"])
def test_job_id_traversal_is_rejected_by_the_handler(logged_in, bad):
    """These REACH the handler and must be turned away by _JOB_ID_RE.

    A 400 rather than a 404: the id is malformed, and 404 would imply the
    shape was fine and the job merely absent. The backslash case is the one
    that matters -- Flask's converter does not treat it as a separator, but
    os.path.join on Windows does.
    """
    assert_error(logged_in.get(f"/api/v1/jobs/{bad}"), "invalid", 400)


@pytest.mark.parametrize("bad", ["../secrets", "a/b"])
def test_job_ids_containing_a_slash_never_reach_the_handler(logged_in, bad):
    """Also safe, but by a different mechanism, so it gets its own test.

    A '/' splits the URL into segments Flask cannot match against
    /jobs/<job_id>, so routing 404s before any handler runs. Asserting 400
    here would be asserting the wrong defence -- and would start failing if
    the route ever gained a <path:> converter, which is exactly when someone
    needs to notice.
    """
    r = logged_in.get(f"/api/v1/jobs/{bad}")
    assert r.status_code == 404


class _FakeManagerOK:
    """Stands in for the real manager so POST /jobs/tune does not spawn a
    tuning subprocess. Mirrors tests/admin/test_jobs.py, which fakes the same
    seam for the Jinja route -- the argv construction it would have exercised
    is build_tune_args', and that has its own tests."""

    def start(self, kind, args):
        return "job123"


class _FakeManagerBusy:
    def start(self, kind, args):
        raise RuntimeError("job already running")


def _patch_manager(monkeypatch, manager):
    # jobs.py binds the manager into its own namespace at import
    # (`from ...jobs import manager as job_manager`), so the module under
    # test is the patch target -- patching swingbot.admin.jobs.manager would
    # leave this reference pointing at the real one.
    monkeypatch.setattr("swingbot.admin.api_v1.jobs.job_manager", manager)


def test_start_tune_returns_a_job_id(logged_in, monkeypatch):
    _patch_manager(monkeypatch, _FakeManagerOK())
    r = logged_in.post("/api/v1/jobs/tune", json={"strategy": "VWAP"})
    assert r.status_code == 200
    assert r.get_json() == {"job_id": "job123"}


def test_start_tune_is_409_while_another_job_runs(logged_in, monkeypatch):
    """Today's behaviour, preserved. One job at a time is a real constraint --
    two concurrent grids contend for the same CSV cache and the same CPU --
    so a second request is refused rather than queued, and 409 says the
    request was well-formed but the resource is busy."""
    _patch_manager(monkeypatch, _FakeManagerBusy())
    assert_error(logged_in.post("/api/v1/jobs/tune", json={"strategy": "VWAP"}),
                 "conflict", 409)


def test_start_tune_rejects_an_unknown_strategy(logged_in, monkeypatch):
    """build_tune_args' whitelist message reaches the client verbatim: it also
    raises on a validation-window request, and a generic 'invalid' would hide
    which of the two happened."""
    _patch_manager(monkeypatch, _FakeManagerOK())
    assert_error(logged_in.post("/api/v1/jobs/tune", json={"strategy": "Nope"}),
                 "invalid", 400)


def test_job_detail_carries_a_log_tail(logged_in, monkeypatch):
    """The reason the SPA needs no second round trip for progress. Refetched
    on the `jobs` event in sub-project 2, replacing the Tuning page's poll."""
    class _Mgr:
        def status(self, job_id):
            return {"id": job_id, "state": "running"}

        def tail(self, job_id, n=100):
            return "line one\nline two"

    _patch_manager(monkeypatch, _Mgr())
    body = logged_in.get("/api/v1/jobs/job123").get_json()
    assert_shape(body, {"id": str, "state": str, "log_tail": str})
    assert body["log_tail"] == "line one\nline two"


def test_list_proposals_empty(logged_in):
    assert_shape(logged_in.get("/api/v1/analytics/tuning/proposals").get_json(),
                 {"proposals": list})


def test_delete_a_proposal(logged_in, proposals_dir):
    (proposals_dir / "20260808120000-rsi.json").write_text(
        json.dumps({"strategy": "RSI"}), encoding="utf-8")
    r = logged_in.delete("/api/v1/analytics/tuning/proposals/20260808120000-rsi.json")
    assert r.status_code == 200
    assert not (proposals_dir / "20260808120000-rsi.json").exists()


def test_delete_unknown_proposal_is_404(logged_in, proposals_dir):
    assert_error(
        logged_in.delete("/api/v1/analytics/tuning/proposals/nope.json"),
        "not_found", 404)


@pytest.mark.parametrize("bad", ["..\..\evil.json", "sub/evil.json", "evil.txt"])
def test_proposal_filename_traversal_is_rejected(logged_in, proposals_dir, bad, tmp_path):
    victim = tmp_path / "evil.json"
    victim.write_text("do not delete me", encoding="utf-8")
    r = logged_in.delete(f"/api/v1/analytics/tuning/proposals/{bad}")
    assert r.status_code in (400, 404), "must never reach os.remove"
    assert victim.exists(), "a traversal filename deleted a file outside the directory"


def test_create_proposal_needs_a_real_job_and_row(logged_in):
    assert_error(
        logged_in.post("/api/v1/analytics/tuning/proposals",
                       json={"job_id": "nosuch", "row_index": 0}),
        "not_found", 404)


def test_create_proposal_rejects_a_non_integer_row(logged_in):
    assert_error(
        logged_in.post("/api/v1/analytics/tuning/proposals",
                       json={"job_id": "x", "row_index": "abc"}),
        "invalid", 400)


def test_create_proposal_from_a_finished_job(logged_in, admin_app, tmp_path, proposals_dir):
    results = tmp_path / "tuning_results"
    results.mkdir(exist_ok=True)
    (results / "job1.json").write_text(json.dumps({
        "strategy": "RSI Divergence",
        "grid": [{"params": {"rsi_reclaim": 30}, "win_rate": 55.0, "n": 40}],
    }), encoding="utf-8")

    r = logged_in.post("/api/v1/analytics/tuning/proposals",
                       json={"job_id": "job1", "row_index": 0})
    assert r.status_code == 200
    body = r.get_json()
    assert_shape(body, {"filename": str, "proposal": dict})
    assert body["proposal"]["proposed_params"] == {"rsi_reclaim": 30}
    assert "validation" in body["proposal"]["note"].lower(), (
        "the note is what stops a proposal being mistaken for an applied change"
    )
    assert (proposals_dir / body["filename"]).exists()
