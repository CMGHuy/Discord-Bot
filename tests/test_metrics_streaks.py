from swingbot.core.analytics.metrics import streaks


def _t(status, closed_at):
    return {"status": status, "closed_at": closed_at}


def test_streaks_basic_sequence():
    # W W L W W W, in chronological order
    closed = [_t("win", "2026-01-01"), _t("win", "2026-01-02"), _t("loss", "2026-01-03"),
              _t("win", "2026-01-04"), _t("win", "2026-01-05"), _t("win", "2026-01-06")]
    s = streaks(closed)
    assert s == {"current": 3, "current_kind": "win", "best_win_streak": 3, "worst_loss_streak": 1}


def test_manual_close_breaks_streak_without_starting_one():
    closed = [_t("win", "2026-01-01"), _t("closed", "2026-01-02"), _t("win", "2026-01-03")]
    s = streaks(closed)
    # the manual close resets current progress but "closed" is never itself
    # a win or loss streak -- the two wins around it are separate 1-streaks.
    assert s["current"] == 1 and s["current_kind"] == "win"
    assert s["best_win_streak"] == 1


def test_streaks_empty():
    assert streaks([]) == {"current": 0, "current_kind": None, "best_win_streak": 0, "worst_loss_streak": 0}


def test_streaks_unsorted_input_is_sorted_internally():
    closed = [_t("loss", "2026-01-03"), _t("win", "2026-01-01"), _t("win", "2026-01-02")]
    s = streaks(closed)
    assert s == {"current": 1, "current_kind": "loss", "best_win_streak": 2, "worst_loss_streak": 1}
