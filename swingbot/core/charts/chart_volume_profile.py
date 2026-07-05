"""
Draws the left-side Volume Profile histogram panel added to every trade
chart -- see trade_chart.generate_trade_chart(), which calls
_draw_volume_profile_panel() last, right before saving the figure, so it
always inherits the price panel's final y-axis. Split out of
trade_chart.py since this is a large, self-contained unit (its own
matplotlib Axes, added via fig.add_axes(), independent of the rest of
that module's figure-assembly code).
"""
import pandas as pd

from .chart_style import (
    ENTRY_COLOR, MUTED_TEXT_COLOR, VOLUME_PROFILE_COLOR,
    VOLUME_PROFILE_PANEL_BINS, VOLUME_PROFILE_PANEL_GAP_FRAC,
    VOLUME_PROFILE_PANEL_LOOKBACK_DAYS, VOLUME_PROFILE_PANEL_WIDTH_FRAC,
    _label_bbox,
)
from ..strategy import compute_volume_profile


def _draw_volume_profile_panel(fig, ax, df: pd.DataFrame, lookback: int, entry_price: float = None,
                                price_range: tuple = None) -> None:
    """
    Adds a Volume Profile histogram panel immediately to the LEFT of the
    price panel `ax` -- a horizontal bar per price bucket, its length
    proportional to how much volume traded at that price, bars growing
    away from the price panel (mirroring how market-profile charts are
    conventionally drawn). The busiest bucket (the Point of Control) is
    drawn fully opaque; every other bucket is drawn at reduced opacity so
    the POC still reads as the standout feature of the shape. If
    `entry_price` falls within the profiled range, the bucket it lands
    in is outlined and a dashed guide line + label mark exactly where
    the planned entry sits relative to the volume distribution (e.g.
    "entering into the POC" vs. "entering into a low-volume pocket").

    `price_range`, if given, is the (lo, hi) the buckets are forced to
    span -- pass the price panel's own final `ax.get_ylim()` (as
    generate_trade_chart does) so the profile always covers the FULL
    visible price axis, edge to edge, with no unbinned stretch left
    blank. Without this, buckets were only as tall as the recent lookback
    window's own High/Low range, which routinely doesn't reach an entry,
    stop, or target sitting well away from where price has recently
    traded (entries are often a deliberate pullback/retest level, not
    simply "now") -- exactly the gap this parameter closes. `lookback` is
    also widened internally (see VOLUME_PROFILE_PANEL_LOOKBACK_DAYS) so
    there's enough trading history to actually populate that wider range
    with real volume instead of manufacturing an empty-looking panel.

    This is a real matplotlib Axes added to the SAME figure via
    fig.add_axes(...) rather than a separate composited image, using
    `sharey=ax` so its price scale is ALWAYS pixel-identical to the
    price panel's, including after ax.set_ylim() is adjusted to fit
    every level/label on the chart -- sharing the axis makes that
    automatic instead of needing to recompute/resync a separately-drawn
    y-scale by hand. Must be called AFTER ax.set_ylim() has been set to
    its final value (i.e. near the end of chart construction, right
    before the figure is saved) so the shared scale it inherits is the
    real one, not a stale default.

    Silently does nothing if there isn't enough history for a profile
    (see compute_volume_profile) -- the rest of the chart is unaffected.
    """
    # Use whichever is longer: the caller's own lookback, or the panel's
    # generous default -- capped at however much history actually
    # exists (compute_volume_profile itself no-ops if that's still too
    # short for even 1 bar of margin).
    panel_lookback = min(len(df), max(lookback, VOLUME_PROFILE_PANEL_LOOKBACK_DAYS))
    price_min, price_max = price_range if price_range else (None, None)
    profile = compute_volume_profile(df, panel_lookback, n_bins=VOLUME_PROFILE_PANEL_BINS,
                                      price_min=price_min, price_max=price_max)
    if profile is None:
        # A caller-supplied range can occasionally be degenerate (e.g. a
        # single flat bar); fall back to the panel's own natural range
        # rather than showing nothing at all.
        profile = compute_volume_profile(df, panel_lookback, n_bins=VOLUME_PROFILE_PANEL_BINS)
    if profile is None:
        return

    price_pos = ax.get_position()
    gap = VOLUME_PROFILE_PANEL_GAP_FRAC
    vp_width = VOLUME_PROFILE_PANEL_WIDTH_FRAC
    vp_left = max(0.01, price_pos.x0 - vp_width - gap)
    # Use whatever room actually exists between the figure's left edge and
    # the price panel (set up front by generate_trade_chart's
    # fig.subplots_adjust(left=...)) rather than assuming vp_width fits
    # exactly -- keeps this robust if that margin ever changes.
    vp_width = max(0.01, price_pos.x0 - gap - vp_left)
    vp_ax = fig.add_axes([vp_left, price_pos.y0, vp_width, price_pos.height], sharey=ax)

    bin_edges = profile["bin_edges"]
    bin_volumes = profile["bin_volumes"]
    poc_index = profile["poc_index"]
    n_bins = len(bin_volumes)
    bin_size = bin_edges[1] - bin_edges[0]
    centers = [bin_edges[i] + bin_size / 2 for i in range(n_bins)]

    # Which bucket the planned entry price falls into, if any -- lets the
    # entry bar be visually distinguished from an ordinary bucket AND from
    # the POC, even when they're the same bucket (outline + fill both).
    # With `price_range` now forcing the buckets to span the price panel's
    # FULL visible axis, entry_price is always within [bin_edges[0],
    # bin_edges[-1]] by construction (it's one of the values the panel's
    # own y-limits were padded around) -- this always finds a bucket for
    # it now, not just when entry happened to sit inside the recent
    # trading range.
    entry_index = None
    if entry_price is not None and bin_edges[0] <= entry_price <= bin_edges[-1]:
        entry_index = min(int((entry_price - bin_edges[0]) / bin_size), n_bins - 1)

    # A bucket genuinely can have zero traded volume (e.g. a bucket out
    # near the padded edge of the axis, or a level that's never actually
    # traded) -- drawing it at true zero width makes it visually
    # indistinguishable from a bucket that was never binned at all (the
    # exact "gap" this panel now guards against). A small visible floor,
    # scaled off the busiest bucket, keeps every price along the axis
    # showing SOME bar -- confirming it was accounted for -- while still
    # leaving the real high-volume bars clearly dominant.
    max_vol = max(bin_volumes) if bin_volumes else 0.0
    min_visible = max_vol * 0.018 if max_vol > 0 else 0.0

    for i, (center, volume) in enumerate(zip(centers, bin_volumes)):
        is_poc = i == poc_index
        is_entry = i == entry_index
        is_floor = volume < min_visible
        draw_volume = min_visible if is_floor else volume
        alpha = 0.9 if (is_poc or is_entry) else (0.22 if is_floor else 0.45)
        edgecolor = ENTRY_COLOR if is_entry else "none"
        linewidth = 1.4 if is_entry else 0
        vp_ax.barh(center, draw_volume, height=bin_size * 0.92, color=VOLUME_PROFILE_COLOR,
                   alpha=alpha, edgecolor=edgecolor, linewidth=linewidth, zorder=3 if is_entry else 2)

    # Bars grow away from the price panel (x=0 at the boundary shared with
    # it) -- the conventional market-profile orientation, and the one
    # shown in the reference layout this panel is modeled on.
    vp_ax.invert_xaxis()
    vp_ax.set_ylim(ax.get_ylim())

    # Per-bucket price labels -- one small tick label per bar showing the
    # exact price that bucket represents, so the granularity actually
    # reads as granular (rather than only ever labeling the POC/Entry
    # bars) as VOLUME_PROFILE_PANEL_BINS is turned up. Drawn as real
    # y-axis tick labels (outside the axes' own drawing area, on this
    # panel's outer-left edge) rather than in-axes text, so they never
    # collide with the "Volume Profile" title or the POC/Entry labels
    # (which sit INSIDE the axes, right-aligned against its right edge
    # next to the price panel) -- and fig.savefig(..., bbox_inches="tight")
    # automatically widens the saved image to fit them without needing
    # any dedicated figure margin reserved up front.
    vp_ax.set_yticks(centers)
    vp_ax.set_yticklabels([f"{c:.2f}" for c in centers])
    vp_ax.tick_params(axis="y", left=False, labelleft=True, labelsize=5.0,
                       labelcolor=MUTED_TEXT_COLOR, pad=2)
    # The price scale itself is still also shown on the price panel (shared
    # y-axis) -- these per-bucket labels are extra granularity, not a
    # replacement -- and the volume (x) scale isn't precise enough to be
    # worth reading exactly, just the shape. Keep that axis visually quiet.
    vp_ax.tick_params(axis="x", labelbottom=False, bottom=False)
    for side in ("top", "left", "bottom"):
        vp_ax.spines[side].set_visible(False)
    vp_ax.spines["right"].set_alpha(0.3)
    vp_ax.patch.set_alpha(0)

    vp_ax.text(0.05, 0.985, "Volume\nProfile", transform=vp_ax.transAxes,
               fontsize=7, color=MUTED_TEXT_COLOR, fontweight="bold", va="top", ha="left",
               linespacing=1.3, alpha=0.9, clip_on=True)

    poc_price = profile["poc_price"]
    poc_pct = profile["poc_pct"]
    ylim = vp_ax.get_ylim()
    y_span = abs(ylim[1] - ylim[0]) or 1.0

    # Both labels are right-aligned against the panel's OWN right edge
    # (ha="right", x just inside 1.0) so the text grows leftward, away
    # from the price panel next door, instead of growing rightward off
    # the end of this narrow axes -- with the default left-alignment,
    # text has no clipping by default and happily renders past its own
    # axes' boundary, which was bleeding into (and colliding with) the
    # price panel's overlay legend whenever the entry or POC price
    # happened to land near the same height as it. clip_on=True is a
    # second line of defense in case a label is still too wide for the
    # panel at its given fontsize.
    poc_va = "center"
    poc_y = poc_price
    if entry_index is not None and abs(poc_index - entry_index) <= 1:
        poc_y = poc_price + y_span * 0.035
        poc_va = "bottom"
    vp_ax.text(0.95, poc_y, f"POC {poc_price:.2f} ({poc_pct:.0f}%) ",
               fontsize=6.5, color=VOLUME_PROFILE_COLOR, fontweight="bold",
               va=poc_va, ha="right", alpha=0.95, zorder=6, clip_on=True,
               bbox=_label_bbox(VOLUME_PROFILE_COLOR, alpha=0.75))

    if entry_index is not None:
        entry_vol_pct = (bin_volumes[entry_index] / sum(bin_volumes) * 100) if sum(bin_volumes) else 0.0
        # Dashed guide line across the full width of the panel at the exact
        # entry price -- makes it unambiguous which bar the entry lands on
        # even when the bucket is thin or near the panel's edge.
        vp_ax.axhline(entry_price, color=ENTRY_COLOR, linewidth=1.1, linestyle="--", alpha=0.85, zorder=5)
        entry_va = "top" if abs(poc_index - entry_index) <= 1 else "center"
        entry_y = entry_price - y_span * 0.035 if entry_va == "top" else entry_price
        vp_ax.text(0.95, entry_y, f"Entry {entry_price:.2f} ({entry_vol_pct:.0f}%) ",
                   fontsize=6.5, color=ENTRY_COLOR, fontweight="bold",
                   va=entry_va, ha="right", alpha=0.95, zorder=6, clip_on=True,
                   bbox=_label_bbox(ENTRY_COLOR, alpha=0.75))
