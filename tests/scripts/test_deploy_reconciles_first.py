"""deploy/deploy.sh must reconcile before the bot comes back up.

Not a style check -- an ordering check. Every push to main runs this script
over SSH (.github/workflows/deploy.yml), and it used to go straight to
`docker compose up -d --build --wait`, which recreates the bot container. A
restart on an unreconciled book re-books plans at CURRENT spot instead of the
price that triggered them: on 2026-08-04 that turned a real 10W/12L into a
flattering 15W/9L across 28 plans, silently, with nothing in the logs.

The steps are individually obvious and the ORDER is the part that is easy to
get wrong in a later edit, so the order is what these tests pin.
"""
import os
import re
import stat

DEPLOY_SH = os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "deploy.sh")


def _script() -> str:
    """Executable lines only.

    The header comment deliberately spells out the failure mode, including the
    old `docker compose up -d --build --wait` line it warns against -- so a
    naive read of the whole file finds every pattern in the prose, in the
    wrong order, and these ordering assertions become meaningless.
    """
    with open(DEPLOY_SH, encoding="utf-8") as f:
        lines = f.read().split("\n")
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


def _index(pattern: str, text: str) -> int:
    m = re.search(pattern, text)
    assert m, f"deploy.sh no longer contains anything matching {pattern!r}"
    return m.start()


def test_the_bot_is_stopped_before_reconciling():
    """Reconciling under a live PlanManager races it over the same bars."""
    s = _script()
    assert _index(r"compose stop bot", s) < _index(r"reconcile_open_plans\.py", s)


def test_state_is_backed_up_before_any_write():
    """--apply rewrites plans/trades/account/journal. 2026-08-04's recovery
    was only possible because a pre-gap backup existed."""
    s = _script()
    assert _index(r"predeploy-", s) < _index(r"reconcile_open_plans\.py --apply", s)
    for f in ("plans", "trades", "account", "journal"):
        assert f in s, f"deploy.sh no longer backs up data/{f}.json"


def test_a_dry_run_precedes_the_apply():
    s = _script()
    dry = _index(r"reconcile_open_plans\.py\n?", s)
    apply_at = _index(r"reconcile_open_plans\.py --apply", s)
    assert dry < apply_at


def test_reconcile_happens_before_the_bot_is_started():
    """The regression this file exists for."""
    s = _script()
    assert _index(r"reconcile_open_plans\.py --apply", s) < _index(r"compose up -d", s)


def test_the_start_step_does_not_rebuild_behind_the_reconcile():
    """`up -d --build` would rebuild AND recreate in one step. The build has
    to happen before the bot is stopped, or the reconcile runs against a
    stale image and the restart is no longer the last thing that happens."""
    s = _script()
    assert "compose up -d --build" not in s, (
        "deploy.sh is back to building and restarting in a single step -- "
        "that is the unreconciled-restart bug"
    )
    assert _index(r"compose build", s) < _index(r"compose stop bot", s)


def test_a_failed_reconcile_leaves_the_bot_down():
    """Uptime is recoverable; a corrupted trade record is not."""
    s = _script()
    assert "RECONCILE FAILED" in s
    tail = s[_index(r"RECONCILE FAILED", s):]
    assert "exit 1" in tail


def test_the_script_reexecs_itself_after_the_pull():
    """Otherwise a fix to the deploy procedure only takes effect on the deploy
    AFTER the one that ships it -- which is exactly how this bug survived."""
    s = _script()
    assert _index(r"git reset --hard", s) < _index(r"SWINGBOT_DEPLOY_REEXEC", s)
    assert re.search(r"exec bash \"\$0\"", s), "no re-exec of the pulled script"


def test_deploy_sh_is_executable():
    assert os.stat(DEPLOY_SH).st_mode & stat.S_IXUSR
