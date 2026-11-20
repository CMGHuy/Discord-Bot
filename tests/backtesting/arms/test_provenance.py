import pytest

from swingbot.core.backtesting.arms import provenance as pv
from swingbot.core.backtesting.arms.windows import ALL_HORIZONS

UNIVERSE = ["AAA", "BBB", "CCC"]


def stamp(**over):
    kw = dict(stage="selection", signal_window=("2018-06-01", "2022-12-31"),
              universe=UNIVERSE, horizons=ALL_HORIZONS, engines=("confluence", "strategy"),
              knob_delta={"MIN_REWARD_PCT": 4.0}, engine_hash_baseline="h",
              engine_hash_component="h", changed_outcomes=12)
    kw.update(over)
    return {"provenance": pv.build_stamp(**kw)}


def test_good_stamp_passes():
    assert pv.check_stamp(stamp(), funnel_stage="mde", full_universe=UNIVERSE) is None


@pytest.mark.parametrize("blob,funnel_stage,token", [
    ({"baseline": []}, "mde", "refused:unstamped"),
    (stamp(stage="pilot"), "mde", "refused:stage-mismatch"),
    (stamp(engine_hash_component="other"), "mde", "refused:engine-mismatch"),
    (stamp(signal_window=("2018-06-01", "2024-03-01")), "mde", "refused:window-contact"),
    (stamp(universe=UNIVERSE[:2]), "mde", "refused:narrow-universe"),
    (stamp(horizons=ALL_HORIZONS[:3]), "mde", "refused:narrow-universe"),
])
def test_each_refusal_token(blob, funnel_stage, token):
    assert pv.check_stamp(blob, funnel_stage=funnel_stage, full_universe=UNIVERSE) == token
    assert token in pv.REFUSAL_TOKENS


def test_pilot_may_be_narrow():
    blob = stamp(stage="pilot", signal_window=("2018-06-01", "2020-12-31"), universe=["AAA"])
    assert pv.check_stamp(blob, funnel_stage="reachability", full_universe=UNIVERSE) is None


def test_validation_may_touch_the_validation_window():
    blob = stamp(stage="validation", signal_window=("2024-01-01", "2025-12-31"))
    assert pv.check_stamp(blob, funnel_stage="validation", full_universe=UNIVERSE) is None


def test_code_hash_tracks_file_content(tmp_path):
    (tmp_path / "a.py").write_text("x = 1\n")
    first = pv.code_hash(tmp_path)
    assert pv.code_hash(tmp_path) == first
    (tmp_path / "a.py").write_text("x = 2\n")
    assert pv.code_hash(tmp_path) != first


# --- v238: the r_basis stamp and its refusal -----------------------------------------

from swingbot.core.backtesting.arms import net_basis  # noqa: E402

TODAYS_KEYS = {"producer", "producer_version", "stage", "signal_window", "universe", "universe_count",
               "horizons", "engines", "knob_delta", "engine_hash", "changed_outcomes",
               "preregistration", "git_head", "created_at"}


def test_a_stamp_without_a_basis_is_key_for_key_todays_stamp():
    assert set(stamp()["provenance"]) == TODAYS_KEYS
    assert set(stamp(r_basis=None)["provenance"]) == TODAYS_KEYS


@pytest.mark.parametrize("basis", ["net", "gross"])
def test_a_basis_is_written_under_its_key_beside_todays_keys(basis):
    prov = stamp(r_basis=basis)["provenance"]
    assert prov[pv.R_BASIS_KEY] == basis
    assert set(prov) == TODAYS_KEYS | {"r_basis"}


def test_build_stamp_refuses_an_unknown_basis():
    with pytest.raises(ValueError, match="r_basis"):
        stamp(r_basis="NET")


def test_the_r_basis_constants_are_the_contract():
    assert pv.R_BASIS_KEY == "r_basis"
    assert pv.R_BASES == ("net", "gross")
    assert pv.R_BASES is net_basis.R_BASES
    assert pv.R_BASIS_REFUSAL == "refused:r-basis"


def test_the_basis_token_is_appended_last_and_the_others_keep_their_order():
    assert pv.REFUSAL_TOKENS == ("refused:unstamped", "refused:stage-mismatch", "refused:engine-mismatch",
                                 "refused:window-contact", "refused:narrow-universe", "refused:zero-diff",
                                 "refused:r-basis")


def test_check_r_basis_passes_a_net_stamp():
    assert pv.check_r_basis(stamp(r_basis="net")) is None


@pytest.mark.parametrize("blob", [
    stamp(),                                              # today's stamp: no key
    stamp(r_basis="gross"),
    {"baseline": [], "component": []},                    # unstamped
    {"provenance": None},
    {"provenance": {"r_basis": ["net"]}},                 # malformed
    {"provenance": {"r_basis": "Net"}},
], ids=["no-key", "gross", "unstamped", "null-provenance", "list-value", "wrong-case"])
def test_check_r_basis_refuses_anything_but_net(blob):
    assert pv.check_r_basis(blob) == pv.R_BASIS_REFUSAL
    assert pv.R_BASIS_REFUSAL in pv.REFUSAL_TOKENS


def test_check_r_basis_honours_the_required_basis():
    assert pv.check_r_basis(stamp(r_basis="gross"), required="gross") is None
    assert pv.check_r_basis(stamp(r_basis="net"), required="gross") == pv.R_BASIS_REFUSAL


@pytest.mark.parametrize("basis", [None, "net", "gross"])
def test_check_stamp_never_reads_the_basis(basis):
    assert pv.check_stamp(stamp(r_basis=basis), funnel_stage="mde", full_universe=UNIVERSE) is None
