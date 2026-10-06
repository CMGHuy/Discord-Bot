"""v136 rule 1: the v1 instrument is byte-identical until cutover.

The golden was captured by v137 IC1 on unmodified code. A failure here means v1
output moved. Find the commit that moved it; do not regenerate the file to make
this pass (see golden.py). A code-default change made elsewhere in config.py
also moves it. Record that decision in the commit that regenerates the file.
"""
import json

import pytest

from tests.backtesting.instrument.golden import CONFIGS, golden_text, render_v1_golden
from tests.backtesting.test_pullback_dryup_witness import pin_code_defaults


def _first_difference(expected: str, actual: str) -> str:
    for n, (want, got) in enumerate(zip(expected.splitlines(), actual.splitlines()), 1):
        if want != got:
            return f"line {n}:\n  golden:  {want[:400]}\n  current: {got[:400]}"
    return f"line counts differ: golden {expected.count(chr(10))}, current {actual.count(chr(10))}"


def test_the_golden_pins_real_trades_under_every_config():
    records = [json.loads(line) for line in golden_text().splitlines()]
    with_trades = {tuple(r["case"])[3] for r in records if "trade" in r}
    assert with_trades == {name for name, _ in CONFIGS}


@pytest.mark.slow
def test_v1_instrument_output_is_byte_identical_to_the_pinned_golden(monkeypatch):
    pin_code_defaults(monkeypatch)
    expected, actual = golden_text(), render_v1_golden()
    assert actual == expected, _first_difference(expected, actual)
