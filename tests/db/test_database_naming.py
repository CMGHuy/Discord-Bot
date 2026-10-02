"""Pure naming tests: no database server is touched.

The shared test container serves every checkout and every concurrent session, so
a database name that is not unique per checkout lets two suite runs wipe each
other's schemas.  These tests pin the naming rule that prevents it.
"""
import pathlib

import sqlalchemy as sa

from tests.db import conftest as dbc

LIMIT = 63  # Postgres identifier limit, in bytes


def test_same_checkout_path_gives_the_same_token():
    path = pathlib.Path("/work/a")
    assert dbc._checkout_token(path) == dbc._checkout_token(path)


def test_different_checkout_paths_give_different_tokens():
    assert dbc._checkout_token(pathlib.Path("/work/a")) != dbc._checkout_token(pathlib.Path("/work/b"))


def test_token_is_eight_lowercase_hex_characters():
    token = dbc._checkout_token(pathlib.Path("/work/a"))
    assert len(token) == 8
    assert token == token.lower()
    int(token, 16)


def test_default_token_does_not_depend_on_cwd(monkeypatch, tmp_path):
    before = dbc._checkout_token()
    monkeypatch.chdir(tmp_path)
    assert dbc._checkout_token() == before


def test_worker_serial_and_empty_names_are_distinct_and_carry_the_token():
    token = "deadbeef"
    names = {
        dbc._database_name("swingbot_test", token, worker, suffix)
        for worker in ("gw0", "gw3", None)
        for suffix in ("", "_empty")
    }
    assert len(names) == 6
    assert all(token in name for name in names)


def test_two_checkouts_never_share_a_name():
    for worker in ("gw0", "gw3", None):
        for suffix in ("", "_empty"):
            assert dbc._database_name("swingbot_test", "aaaaaaaa", worker, suffix) != \
                dbc._database_name("swingbot_test", "bbbbbbbb", worker, suffix)


def test_longest_default_name_fits_the_identifier_limit():
    base = sa.engine.make_url(dbc.DEFAULT_TEST_URL).database
    name = dbc._database_name(base, dbc._checkout_token(), "gw12", "_empty")
    assert len(name.encode()) <= LIMIT


def test_very_long_base_is_truncated_but_token_and_suffix_survive():
    name = dbc._database_name("x" * 200, "deadbeef", "gw3", "_empty")
    assert len(name.encode()) <= LIMIT
    assert "deadbeef" in name and name.endswith("_gw3_empty")
