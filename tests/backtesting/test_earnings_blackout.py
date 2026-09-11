import dataclasses
from swingbot.core.backtesting import earnings_blackout as eb
from swingbot.core.backtesting.acceptance import ArmTrade

def rows(*groups):
    result=[]
    for i, (outcome, distance) in enumerate(groups):
        result.append(eb.ExposureRow(ArmTrade("AAA", "S", "4w", f"2019-01-{i + 1:02d}", outcome, 1.5 if outcome == "win" else -1.0, 2.0), "strategy", False, distance is not None, 100 + i, distance))
    return result

def test_constants_and_split():
    sample = rows(("win", None), ("loss", 1), ("loss", 2), ("win", 6))
    assert eb.GRID == (1, 2, 3, 5) and eb.COVERAGE_FLOOR_PCT == 90.0
    assert [len(part) for part in eb.split(sample, 2)] == [4, 2, 2]

def test_coverage_and_roundtrip():
    sample=rows(("win", 1), ("loss", None))
    assert eb.coverage_pct(sample) == 50.0
    assert eb.ExposureRow.from_dict(sample[0].to_dict()) == sample[0]

def test_candidate_and_permutation_are_deterministic():
    sample = rows(*([("win", None)] * 10 + [("loss", None)] * 6 + [("loss", 1)] * 4))
    candidate=eb.score_candidate(sample, 1)
    assert candidate.eligible and candidate.removed_n == 4
    reactions={"AAA": [row.signal_pos + row.distance for row in sample if row.distance is not None]}
    assert eb.permutation_test(sample, 1, reactions, 1000, n=20) == eb.permutation_test(sample, 1, reactions, 1000, n=20)
