"""v73 runners with no TP2 retain nulls-last sorting in both directions."""
import swingbot.admin.app

from swingbot.admin.api_v1.trades import _sorted_rows


def rows():
    return [{"id": "a", "target": 140.0}, {"id": "b", "target": None},
            {"id": "c", "target": 120.0}]


def test_nulls_sort_last_ascending():
    assert [row["id"] for row in _sorted_rows(rows(), "target", False)] == ["c", "a", "b"]


def test_nulls_sort_last_descending_too():
    assert [row["id"] for row in _sorted_rows(rows(), "target", True)] == ["a", "c", "b"]


def test_all_null_column_does_not_raise():
    only_nulls = [{"id": "a", "target": None}, {"id": "b", "target": None}]
    assert len(_sorted_rows(only_nulls, "target", True)) == 2
