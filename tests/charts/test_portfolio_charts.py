# tests/test_portfolio_charts.py
import matplotlib
import pytest
from tests.conftest import assert_rendered

# ~85% of suite runtime lives in nine files like this one; excluded from
# the fast tier (scripts/dev/testrun.py fast). See docs/claude/testing-cost.md.
pytestmark = pytest.mark.slow
matplotlib.use("Agg")


def test_mc_fan_renders(tmp_path):
    from swingbot.core.edge.ruin import simulate
    from swingbot.core.charts.portfolio_charts import render_mc_fan
    sim = simulate([0.4] * 8 + [-1.0] * 2, risk_pct=1.0,
                   n_trades=300, n_paths=500, return_paths=True)
    path = render_mc_fan(sim, 10_000.0, str(tmp_path),
                         percentile_paths=sim["percentile_paths"])
    assert_rendered(path)


def test_save_closes_figure_even_if_savefig_raises(tmp_path, monkeypatch):
    """A savefig failure (disk full, bad path, encoder error) must not leak
    the matplotlib Figure in this long-running bot process."""
    import matplotlib.pyplot as plt
    from swingbot.core.charts.portfolio_charts import _save

    def _boom(*a, **kw):
        raise RuntimeError("disk full")

    fig, ax = plt.subplots()
    fignum = fig.number
    monkeypatch.setattr(fig, "savefig", _boom)

    with pytest.raises(RuntimeError):
        _save(fig, str(tmp_path), "test.png")

    assert fignum not in plt.get_fignums()


def test_every_renderer_saves_through_the_disclaimer_helper():
    """Task E97: _save() is the ONLY place DISCLAIMER_TEXT gets drawn onto a
    portfolio chart -- if any render_* function called fig.savefig directly
    instead of returning _save(...), that chart would silently ship without
    the risk disclosure. Source-grepped rather than pixel-checked because
    the disclaimer text is 6pt, near-invisible in a saved-PNG byte-size
    assertion, and this is a structural guarantee, not a rendering one."""
    import inspect
    from swingbot.core.charts import portfolio_charts as pc

    src = inspect.getsource(pc)
    # Exactly one real fig.savefig call in the whole module -- inside _save().
    assert src.count("fig.savefig(") == 1
    for name, fn in inspect.getmembers(pc, inspect.isfunction):
        if name.startswith("render_"):
            assert "return _save(" in inspect.getsource(fn), \
                f"{name} does not return through _save() -- would ship without the disclaimer"
