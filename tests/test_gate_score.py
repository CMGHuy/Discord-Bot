from swingbot.core.gate.score import assign_tier, score
from swingbot.core.gate.types import CheckResult


def _c(status, weight, cid="c"):
    return CheckResult(cid, "setup", status, weight, "", {})


def test_golden_mixed_score():
    # (10*1 + 10*1 + 10*0.5 + 10*0 = 25) / 40 * 100 = 62.5 — unknown w=50 excluded.
    # NB: the plan wrote the fail check's weight as 20 while summing its
    # denominator as 40; 20 would give 25/50 = 50.0, which also collides with
    # the neutral "nothing scoreable" value and would make this golden useless.
    # Weight 10 is what the plan's own arithmetic and expected 62.5 require.
    checks = [_c("pass", 10, "a"), _c("pass", 10, "b"), _c("warn", 10, "w"),
              _c("fail", 10, "f"), _c("unknown", 50, "u")]
    assert score(checks) == 62.5


def test_fail_weight_counts_in_denominator():
    # Guards the reading the golden above disambiguates: a failing check keeps
    # its weight in the denominator (unlike unknown, which is excluded).
    assert score([_c("pass", 10, "a"), _c("fail", 30, "f")]) == 25.0


def test_all_unknown_or_empty_is_neutral_50():
    assert score([_c("unknown", 10), _c("unknown", 20)]) == 50.0
    assert score([]) == 50.0


def test_zero_weight_checks_are_info_only():
    assert score([_c("fail", 0, "info"), _c("pass", 10, "real")]) == 100.0


def test_hard_block_forces_c_even_at_100():
    assert assign_tier(100.0, ["signal_confirmed"],
                       aplus_cut=90.0, a_cut=75.0, b_cut=55.0) == "C"


def test_tier_cut_boundaries():
    kw = dict(aplus_cut=90.0, a_cut=75.0, b_cut=55.0)
    assert assign_tier(95.0, [], **kw) == "A+"
    assert assign_tier(90.0, [], **kw) == "A+"   # cuts are inclusive
    assert assign_tier(80.0, [], **kw) == "A"
    assert assign_tier(60.0, [], **kw) == "B"
    assert assign_tier(54.9, [], **kw) == "C"
