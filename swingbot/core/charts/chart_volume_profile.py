"""
Draws the Volume Profile overlaid inside the price panel of every trade
chart -- see trade_chart.generate_trade_chart(), which calls
_draw_volume_profile_overlay() last, right before saving the figure, so it
always sees the price panel's final y-axis. Split out of trade_chart.py
since this is a large, self-contained unit independent of the rest of that
module's figure-assembly code.

It used to be a detached panel to the LEFT of the price panel, on its own
`fig.add_axes(..., sharey=ax)`. That second axes printed its own dense
per-bucket price ladder, which meant every chart carried two copies of the
price scale. Drawing straight onto the price axes with a blended transform
removes the second axis, and the duplicate ladder with it.
"""
import pandas as pd

from .chart_style import (
    ENTRY_COLOR, VOLUME_PROFILE_COLOR,
    VOLUME_PROFILE_OVERLAY_MAX_FRAC, VOLUME_PROFILE_PANEL_BINS,
    VOLUME_PROFILE_PANEL_LOOKBACK_DAYS,
    _label_bbox,
)
from swingbot.core.market.strategy import compute_volume_profile


def _draw_volume_profile_overlay(ax, df: pd.DataFrame, lookback: int, entry_price: float = None,
                                 price_range: tuple = None) -> None:
    """
    Draws the Volume Profile as an overlay INSIDE the price panel `ax` -- a
    horizontal bar per price bucket, its length proportional to how much
    volume traded at that price, bars growing leftward from the panel's
    right edge (TradingView's "Volume Profile Visible Range" orientation).
    The busiest bucket (the Point of Control) is
    drawn at the highest opacity; every other bucket is drawn fainter so
    the POC still reads as the standout feature of the shape. Everything is
    knocked back further than the old detached panel needed, because these
    bars now sit over live candles and must read as background market
    structure rather than foreground data. If `entry_price` falls within the
    profiled range, the bucket it lands in is outlined and labelled with
    where the planned entry sits relative to the volume distribution (e.g.
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

    Bars are drawn onto `ax` itself through a blended transform (x in axes
    coordinates, y in data coordinates), so the profile's price scale is the
    price panel's own -- pixel-identical by construction, with no second axis
    to resync. Must still be called AFTER ax.set_ylim() has been set to its
    final value (i.e. near the end of chart construction, right before the
    figure is saved): the buckets are binned against that range, so a stale
    limit would bin against the wrong span.

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

    # Bars are drawn straight onto the price axes with a blended transform:
    # width in AXES coordinates (so a full-width bucket spans a fixed fraction
    # of the pane regardless of the price scale), position in DATA coordinates
    # (so each bucket lines up with its real price). This is what lets the
    # profile share the price panel's ladder instead of owning a second one --
    # the duplicate left-hand price ladder this module used to print.
    import matplotlib.transforms as mtransforms
    blended = mtransforms.blended_transform_factory(ax.transAxes, ax.transData)
    vp_ax = ax
    max_frac = VOLUME_PROFILE_OVERLAY_MAX_FRAC

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
        # Bars grow LEFTWARD from the right edge (left=1.0, negative width in
        # axes coordinates) -- TradingView's Volume Profile Visible Range
        # orientation. Alpha is knocked down further than the old detached
        # panel used: this now sits over live candles, so it has to read as
        # background market structure, never as foreground data.
        frac = (draw_volume / max_vol) * max_frac if max_vol > 0 else 0.0
        vp_ax.barh(center, -frac, left=1.0, height=bin_size * 0.92,
                   color=VOLUME_PROFILE_COLOR, alpha=alpha * 0.75,
                   edgecolor=edgecolor, linewidth=linewidth,
                   transform=blended, zorder=3 if is_entry else 2, clip_on=True)

    # The per-bucket y tick labels this module used to print ARE the duplicate
    # price ladder: a second, denser copy of the price scale already shown on
    # the right axis. Sharing the price panel's own axis makes them redundant
    # by construction, so they are gone -- along with the panel spines, the
    # transparent patch, and the "Volume Profile" corner title (whose old spot
    # is now occupied by the top-left legend block). The profile is named on
    # legend line 3 instead.

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
    # x is an AXES fraction, y a real price -- so the blended transform is
    # now required. Before the overlay move these labels lived on their own
    # narrow axes where a bare 0.95 was resolved against that panel's own
    # scale; on the price axes a bare 0.95 would be read as a PRICE.
    vp_ax.text(1.0 - max_frac - 0.01, poc_y, f"POC {poc_price:.2f} ({poc_pct:.0f}%) ",
               fontsize=6.5, color=VOLUME_PROFILE_COLOR, fontweight="bold",
               va=poc_va, ha="right", alpha=0.95, zorder=6, clip_on=True,
               transform=blended, bbox=_label_bbox(VOLUME_PROFILE_COLOR, alpha=0.75))

    if entry_index is not None:
        entry_vol_pct = (bin_volumes[entry_index] / sum(bin_volumes) * 100) if sum(bin_volumes) else 0.0
        # The old dashed guide line at entry_price is gone: on its own narrow
        # panel it was the only thing marking the entry, but on the price axes
        # generate_trade_chart already draws that exact level (and now tags it
        # on the right axis too), so repeating it here would double the line.
        entry_va = "top" if abs(poc_index - entry_index) <= 1 else "center"
        entry_y = entry_price - y_span * 0.035 if entry_va == "top" else entry_price
        vp_ax.text(1.0 - max_frac - 0.01, entry_y, f"Entry {entry_price:.2f} ({entry_vol_pct:.0f}%) ",
                   fontsize=6.5, color=ENTRY_COLOR, fontweight="bold",
                   va=entry_va, ha="right", alpha=0.95, zorder=6, clip_on=True,
                   transform=blended, bbox=_label_bbox(ENTRY_COLOR, alpha=0.75))
