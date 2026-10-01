"""Child-process cases for tests/db/test_fixture_isolation.py -- never collected
by the parent run (the file name does not match ``test_*.py``).

The two tests are order-dependent on purpose: the first commits a row through
the shared engine, the second proves the isolation fixture removed it.
"""
import sqlalchemy as sa


def test_first_commits_a_row_through_the_engine(db_engine):
    with db_engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO ui_preferences (owner) VALUES ('leaky')"))


def test_second_finds_the_table_empty(db_engine):
    with db_engine.connect() as connection:
        left = connection.execute(sa.text("SELECT owner FROM ui_preferences")).scalars().all()
    assert left == [], f"a committed row leaked from the previous test: {left}"
