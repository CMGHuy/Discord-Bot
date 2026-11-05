"""v207: the url_map classification contract (spec § Access check).

Every served rule x method must be in tests/admin/access_expectations.py, and
swingbot.admin.access must agree with every row. A new route fails here until
its author classifies it."""
import pytest
from tests.admin.access_expectations import EXPECTATIONS, SAMPLE_PATHS

from swingbot.admin import access

VIEWER = {"role": "viewer", "username": "viewer1", "user_id": 1}
ADMIN = {"role": "admin", "username": "admin", "user_id": None}
SKIPPED_METHODS = {"HEAD", "OPTIONS"}


def _served(app) -> dict[tuple[str, str], str]:
    return {(rule.rule, method): rule.endpoint
            for rule in app.url_map.iter_rules()
            for method in rule.methods - SKIPPED_METHODS}


def test_every_served_rule_is_classified(admin_app):
    missing = sorted(_served(admin_app).keys() - EXPECTATIONS.keys())
    assert not missing, f"classify in tests/admin/access_expectations.py: {missing}"


def test_no_row_names_a_rule_that_is_gone(admin_app):
    stale = sorted(EXPECTATIONS.keys() - _served(admin_app).keys())
    assert not stale, f"remove from tests/admin/access_expectations.py: {stale}"


def test_kinds_are_the_three_known_ones():
    assert set(EXPECTATIONS.values()) <= {"public", "viewer", "admin"}


def test_every_converter_rule_has_a_sample_path_that_routes_to_it(admin_app):
    served = _served(admin_app)
    adapter = admin_app.url_map.bind("localhost")
    for rule, method in EXPECTATIONS:
        if "<" not in rule:
            continue
        assert rule in SAMPLE_PATHS, f"SAMPLE_PATHS needs {rule!r}"
        endpoint, _args = adapter.match(SAMPLE_PATHS[rule], method=method)
        assert endpoint == served[(rule, method)], (rule, method)


@pytest.mark.parametrize("key", sorted(EXPECTATIONS), ids=lambda key: f"{key[1]} {key[0]}")
def test_check_access_agrees_with_the_table(key):
    rule, method = key
    kind = EXPECTATIONS[key]
    path = SAMPLE_PATHS.get(rule, rule)
    assert access.check_access(ADMIN, method, path) is True
    assert access.check_access(None, method, path) is True
    assert access.check_access(VIEWER, method, path) is (kind != "admin")
    outside_role_check = path in access.EXEMPT_PATHS or not path.startswith("/api/v1/")
    assert outside_role_check is (kind == "public")
