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


# --- SR51: the grid result ------------------------------------------------
#
# The job has always written this file and _load_result has always read it,
# but only the Jinja page rendered it. Without a route the SPA could launch a
# grid and never see what it found -- which also left POST /proposals, which
# takes a job_id and a row_index, unreachable by any normal route.


@pytest.fixture
def results_dir(admin_app, tmp_path):
    d = tmp_path / "tuning_results"
    d.mkdir(exist_ok=True)
    return d


def _write_grid(results_dir, rows, strategy="RSI Divergence"):
    (results_dir / "job1.json").write_text(
        json.dumps({"strategy": strategy, "grid": rows}), encoding="utf-8")


def test_job_result_requires_auth(client):
    assert_error(client.get("/api/v1/jobs/job1/result"), "auth", 401)


@pytest.mark.parametrize("bad", ["..\secrets", "a.b", "a;b"])
def test_job_result_rejects_a_traversal_id(logged_in, bad):
    """Same guard as GET /jobs/<id>: this id also reaches a filesystem path."""
    assert_error(logged_in.get(f"/api/v1/jobs/{bad}/result"), "invalid", 400)


def test_job_result_is_empty_not_404_while_a_job_is_still_running(logged_in, results_dir):
    """A running job has written no result yet, and that is the ordinary case.

    A 404 would have the UI report a failure for "it has not finished",
    which is the reading that sends someone looking for a bug.
    """
    body = logged_in.get("/api/v1/jobs/stillgoing/result").get_json()
    # The empty response carries the same three keys as a full one, so a
    # client never has to branch on which shape it got.
    assert_shape(body, {"job_id": str, "strategy": type(None), "grid": list})
    assert body["grid"] == []


def test_job_result_returns_the_grid(logged_in, results_dir):
    _write_grid(results_dir, [
        {"params": {"rsi_reclaim": 30}, "n_eval": 40, "win_rate": 82.0,
         "expectancy_r": 0.4, "excluded_share": 0.2},
        {"params": {"rsi_reclaim": 35}, "n_eval": 12, "win_rate": 90.0,
         "expectancy_r": 0.6, "excluded_share": 0.1},
    ])
    body = logged_in.get("/api/v1/jobs/job1/result").get_json()

    assert body["strategy"] == "RSI Divergence"
    assert len(body["grid"]) == 2
    assert body["grid"][0]["params"] == {"rsi_reclaim": 30}


def test_job_result_marks_which_rows_cleared_the_bar(logged_in, results_dir):
    """`passes` is computed server-side on purpose.

    The bar is four conditions -- n_eval >= 30, win rate >= 80, positive
    expectancy, excluded share <= 0.5 -- and it is the same bar
    scripts/backtest/tune_strategy.py prints. A second copy of it in TypeScript is how
    the two would come to disagree about which rows are worth taking.
    """
    _write_grid(results_dir, [
        # Clears everything.
        {"params": {"a": 1}, "n_eval": 40, "win_rate": 82.0,
         "expectancy_r": 0.4, "excluded_share": 0.2},
        # Great win rate on far too few trades.
        {"params": {"a": 2}, "n_eval": 12, "win_rate": 90.0,
         "expectancy_r": 0.6, "excluded_share": 0.1},
        # Enough trades, but it threw away most of the candidates to get there.
        {"params": {"a": 3}, "n_eval": 40, "win_rate": 85.0,
         "expectancy_r": 0.4, "excluded_share": 0.9},
        # Wins often and still loses money.
        {"params": {"a": 4}, "n_eval": 40, "win_rate": 81.0,
         "expectancy_r": -0.1, "excluded_share": 0.2},
    ])
    grid = logged_in.get("/api/v1/jobs/job1/result").get_json()["grid"]

    assert [row["passes"] for row in grid] == [True, False, False, False]


def test_job_result_carries_each_row_index(logged_in, results_dir):
    """POST /proposals identifies a row by index. Carrying it on the row means
    a client that sorts or filters the grid still proposes the right one."""
    _write_grid(results_dir, [
        {"params": {"a": 1}, "n_eval": 40, "win_rate": 82.0,
         "expectancy_r": 0.4, "excluded_share": 0.2},
        {"params": {"a": 2}, "n_eval": 40, "win_rate": 83.0,
         "expectancy_r": 0.5, "excluded_share": 0.2},
    ])
    grid = logged_in.get("/api/v1/jobs/job1/result").get_json()["grid"]

    assert [row["row_index"] for row in grid] == [0, 1]


def test_a_row_from_the_result_can_be_proposed(logged_in, results_dir, proposals_dir):
    """The whole point of the endpoint: the loop closes.

    Before SR51 a grid could be launched and proposals could be deleted, but
    nothing could create one -- the Propose button lived in the results table
    that never migrated.
    """
    _write_grid(results_dir, [
        {"params": {"rsi_reclaim": 30}, "n_eval": 40, "win_rate": 82.0,
         "expectancy_r": 0.4, "excluded_share": 0.2},
    ])
    row = logged_in.get("/api/v1/jobs/job1/result").get_json()["grid"][0]

    r = logged_in.post("/api/v1/analytics/tuning/proposals",
                       json={"job_id": "job1", "row_index": row["row_index"]})
    assert r.status_code == 200
    assert r.get_json()["proposal"]["proposed_params"] == {"rsi_reclaim": 30}


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
