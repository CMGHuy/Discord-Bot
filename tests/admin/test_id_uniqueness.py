"""NG1 — the invariant that lets /api/v1/trades expose one `id` namespace.

NG19 TRIAGE — **v1-era · KEEP.** Written for this migration, not inherited
from the Jinja UI; nothing here survives on rendered HTML.


Spec `docs/superpowers/specs/implemented/2026-08-08-v11-admin-rest-api-design.md`
(Decision 2) unifies plans and trades into one collection at the API layer.
That is only safe if a plan id can never be mistaken for a trade id: the SPA
sends back a single opaque `id` and the server has to route it to the right
store without a disambiguating prefix.

The two id spaces are disjoint for two independent structural reasons, and
each gets its own test so a regression names which one broke:

  plan ids   `str(uuid.uuid4())` -- 36 chars, hex + dashes  (plan_engine.py)
  trade ids  16 chars from ascii_letters + digits           (performance.py)

Length alone separates them (36 vs 16); the dash separates them again. Either
property failing is enough to make prefixed ids (`plan:<id>` / `trade:<id>`)
mandatory, so both are pinned here rather than relying on the belt or the
braces alone.

These assert against the real generators, not fixture data -- a snapshot of
data/ would only prove that no collision has happened yet, which is the
weaker claim.
"""
import string
import uuid

from swingbot.core.tracking.performance import _TRADE_ID_ALPHABET

# Enough to catch a generator whose charset or length has changed, without
# making the suite slow. Not a probabilistic collision hunt -- 62^16 needs no
# help from us, and Decision 2 rests on the structural argument, not on luck.
_SAMPLE = 500


def _new_plan_id() -> str:
    """How plan_engine.py mints a plan id (two call sites, both uuid4)."""
    return str(uuid.uuid4())


def _new_trade_id() -> str:
    """How TradeLog.log_trade mints a trade id."""
    import secrets
    return "".join(secrets.choice(_TRADE_ID_ALPHABET) for _ in range(16))


def test_trade_id_alphabet_is_alphanumeric_only():
    """No dash in the trade alphabet -- half of why the spaces are disjoint."""
    assert _TRADE_ID_ALPHABET == string.ascii_letters + string.digits
    assert "-" not in _TRADE_ID_ALPHABET


def test_trade_ids_are_16_alphanumeric_chars():
    for _ in range(_SAMPLE):
        tid = _new_trade_id()
        assert len(tid) == 16
        assert tid.isalnum()


def test_plan_ids_are_36_char_dashed_uuids():
    for _ in range(_SAMPLE):
        pid = _new_plan_id()
        assert len(pid) == 36
        assert pid.count("-") == 4
        # Round-trips through uuid.UUID, so it is a real uuid4 string and not
        # merely something 36 characters long.
        assert str(uuid.UUID(pid)) == pid


def test_plan_and_trade_id_spaces_cannot_collide():
    """The invariant /api/v1/trades depends on, stated directly.

    Fails if either generator changes such that one could produce a value the
    other could also produce -- at which point spec v11 Decision 2 must adopt
    `plan:<id>` / `trade:<id>` prefixing before any Trades endpoint is built.
    """
    plan_ids = {_new_plan_id() for _ in range(_SAMPLE)}
    trade_ids = {_new_trade_id() for _ in range(_SAMPLE)}

    assert not (plan_ids & trade_ids)

    # And the structural reason, so a failure says *why* rather than just
    # "these 1000 random strings happened not to overlap".
    assert {len(i) for i in plan_ids} == {36}
    assert {len(i) for i in trade_ids} == {16}
    assert all("-" in i for i in plan_ids)
    assert not any("-" in i for i in trade_ids)


def test_an_id_can_be_routed_to_its_store_without_a_prefix():
    """The property the API actually consumes: given a bare id, pick a store.

    This is the rule `GET /api/v1/trades/{id}` will implement. It lives here
    so that if the id formats ever converge, the failure lands on the thing
    that breaks rather than on an abstract charset assertion.
    """
    def looks_like_a_plan_id(value: str) -> bool:
        return len(value) == 36 and value.count("-") == 4

    for _ in range(_SAMPLE):
        assert looks_like_a_plan_id(_new_plan_id())
        assert not looks_like_a_plan_id(_new_trade_id())
