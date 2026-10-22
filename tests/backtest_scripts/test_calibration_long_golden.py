"""v182 partner rule: the calibration script's default (long, trail) run
prints the same text, byte for byte, after every v182 task. Golden captured
in V182-1 on the unchanged script."""
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "backtest" / "screen_trail_calibration.py"
GOLDEN = Path(__file__).with_name("golden") / "trail_calibration_v182.txt"
ARGS = ("--replicates", "3", "--tickers", "2", "--resamples", "500",
        "--date", "2026-10-21", "--dry-run")


def run_default() -> str:
    """The script's stdout for ARGS, decoded UTF-8, CRLF folded to LF."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run([sys.executable, str(SCRIPT), *ARGS], cwd=ROOT, env=env,
                         capture_output=True, check=True)
    return out.stdout.decode("utf-8").replace("\r\n", "\n")


def test_default_calibration_output_is_byte_identical_to_the_golden():
    assert run_default() == GOLDEN.read_text(encoding="utf-8")


def test_the_golden_is_the_long_trail_calibration():
    text = GOLDEN.read_text(encoding="utf-8")
    assert text.startswith("# v163 trail race A/A calibration")
    assert "| 20261015 |" in text and "| 20261017 |" in text
