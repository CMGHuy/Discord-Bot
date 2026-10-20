import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';

import { BandQuantiles, BandZone, VarianceBandInsufficient, VarianceBandOk } from '../../../api/models';
import { AnalyticsStore } from '../../../stores/analytics.store';
import { ConnectionStore } from '../../../stores/connection.store';
import { Panel } from '../../../ui/layout';
import { PanelError } from '../../../ui/panel-error';
import { PanelHeader } from '../../../ui/panel-header';
import {
  BAR_LABELS, BandSegment, BandUnit, CAPTION, CAVEAT, HEADER_COPY, PANEL_TITLE, ZONE_COPY,
  bandSegments, barAriaLabel, compositionLine, dollarNote, drawdownMarkerText, exprLine,
  insufficientCopy, markerPercent, runMarkerText, secondaryText, spanText, uncertaintyText,
} from './variance-band.model';

/** One bar, fully resolved: the template only lays it out. */
interface BarView {
  key: 'run' | 'drawdown';
  label: string;
  segments: BandSegment[];
  marker: number;
  markerText: string;
  zone: BandZone;
  zoneText: string;
  uncertainty: string;
  aria: string;
}

export interface BandView {
  bars: BarView[];
  span50: string;
  span20: string;
  secondary: string;
  expr: string;
  caveat: string | null;
  composition: string;
  dollarNote: string | null;
}

function barView(
  key: BarView['key'], q: BandQuantiles, unit: BandUnit, value: number, markerText: string, zone: BandZone,
): BarView {
  const label = BAR_LABELS[key];
  const segments = bandSegments(q, unit);
  return {
    key, label, segments, marker: markerPercent(value, q), markerText, zone,
    zoneText: ZONE_COPY[zone], uncertainty: uncertaintyText(q, unit),
    aria: barAriaLabel(label, segments, markerText),
  };
}

/** The whole panel's text and geometry for one `ok` band. The bars are
 *  placed against the LAST horizon (50 close days), the one the current
 *  state is zoned against; the first (20) is the secondary line. */
export function bandView(band: VarianceBandOk, currency: string): BandView {
  const h20 = band.horizons[0];
  const h50 = band.horizons[band.horizons.length - 1];
  const cur = band.current;
  return {
    bars: [
      barView('run', h50.run, 'days', cur.run, runMarkerText(cur), cur.run_zone),
      barView('drawdown', h50.drawdown, 'R', cur.drawdown, drawdownMarkerText(cur, band.dollars, currency), cur.drawdown_zone),
    ],
    span50: spanText(h50),
    span20: spanText(h20),
    secondary: secondaryText(h20),
    expr: exprLine(band.expr),
    caveat: band.expr.not_positive ? CAVEAT : null,
    composition: compositionLine(band.composition),
    dollarNote: band.dollars ? dollarNote(band.dollars, currency) : null,
  };
}

/** v175 "Normal bad luck": where the book's current losing run and 50-day
 *  drawdown sit against the range its own past trades produce by chance.
 *  Whole book, closed trades only; not interactive (Retry aside). */
@Component({
  selector: 'sb-variance-band-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, PanelHeader, PanelError],
  template: `
    <sb-panel>
      <sb-panel-header [title]="title" />
      <p class="scope-line">{{ header }}</p>
      @if (store.varianceBandError(); as error) {
        <sb-panel-error [message]="error" (retry)="store.reload('varianceBand')" />
      } @else if (insufficient(); as band) {
        <p class="insufficient">{{ insufficientText(band) }}</p>
      } @else if (view(); as v) {
        <div class="bars">
          @for (bar of v.bars; track bar.key) {
            <section class="bar" [attr.data-bar]="bar.key">
              <h4 class="bar-label">{{ bar.label }}</h4>
              <div class="track" role="img" [attr.aria-label]="bar.aria">
                @for (seg of bar.segments; track seg.zone) {
                  <span class="seg" [attr.data-zone]="seg.zone" [style.width.%]="seg.width"></span>
                }
                <span class="marker" [style.left.%]="bar.marker"></span>
              </div>
              <ul class="legend">
                @for (seg of bar.segments; track seg.zone) {
                  <li [attr.data-zone]="seg.zone"><span class="key"></span>{{ seg.label }} <span class="num">{{ seg.range }}</span></li>
                }
              </ul>
              <p class="now">{{ bar.markerText }}</p>
              <p class="zone" [attr.data-zone]="bar.zone">{{ bar.zoneText }}</p>
              <p class="meta">{{ bar.uncertainty }}</p>
            </section>
          }
        </div>
        <p class="meta">{{ v.span50 }}</p>
        <p class="meta">{{ v.secondary }}</p>
        <p class="meta">{{ v.span20 }}</p>
        <p class="expr">{{ v.expr }}</p>
        @if (v.caveat) { <p class="caveat" role="note">{{ v.caveat }}</p> }
        <p class="composition">{{ v.composition }}</p>
        @if (v.dollarNote) { <p class="dollar-note">{{ v.dollarNote }}</p> }
        <p class="caption">{{ caption }}</p>
      }
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    p { margin: var(--space-6) 0 0; overflow-wrap: anywhere; }
    .scope-line { font-size: var(--text-chip); color: var(--text-secondary); }
    .bars { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--space-14); margin-top: var(--space-10); }
    .bar { min-width: 0; }
    .bar-label { margin: 0 0 var(--space-6); font-size: var(--text-chip); color: var(--text-secondary); }
    .track { position: relative; display: flex; height: 14px; border-radius: var(--radius-sm); background: var(--bg); }
    .seg { display: block; height: 100%; min-width: 2px; opacity: 0.55; }
    [data-zone='normal'] .key, .seg[data-zone='normal'] { background: var(--pos); }
    [data-zone='rough'] .key, .seg[data-zone='rough'] { background: var(--warn); }
    [data-zone='outside'] .key, .seg[data-zone='outside'] { background: var(--neg); }
    .marker { position: absolute; top: -4px; bottom: -4px; width: 3px; margin-left: -1.5px; border-radius: 2px; background: var(--text); }
    .legend { display: flex; flex-wrap: wrap; gap: var(--space-6) var(--space-14); margin: var(--space-6) 0 0; padding: 0; list-style: none; font-size: var(--text-chip); color: var(--text-secondary); }
    .legend li { display: inline-flex; align-items: center; gap: var(--space-6); min-width: 0; }
    .key { flex: none; width: 10px; height: 10px; border-radius: var(--radius-sm); opacity: 0.55; }
    .num { color: var(--text); font-variant-numeric: tabular-nums; overflow-wrap: anywhere; }
    .now { color: var(--text); font-variant-numeric: tabular-nums; }
    .zone { color: var(--text); font-weight: 600; }
    .meta, .composition, .dollar-note { font-size: var(--text-chip); color: var(--text-secondary); }
    .expr { color: var(--text); font-variant-numeric: tabular-nums; }
    .caveat { color: var(--warn); }
    .insufficient { color: var(--text-secondary); }
    .caption { font-size: var(--text-chip); color: var(--text-faint); }
    @media (max-width: 639px) { .bars { grid-template-columns: 1fr; } }
  `,
})
export class VarianceBandPanel {
  readonly store = inject(AnalyticsStore);
  private readonly connection = inject(ConnectionStore);

  protected readonly title = PANEL_TITLE;
  protected readonly header = HEADER_COPY;
  protected readonly caption = CAPTION;

  protected readonly insufficient = computed<VarianceBandInsufficient | null>(() => {
    const band = this.store.varianceBand();
    return band?.status === 'insufficient' ? band : null;
  });

  protected readonly view = computed<BandView | null>(() => {
    const band = this.store.varianceBand();
    return band?.status === 'ok' ? bandView(band, this.connection.currency()) : null;
  });

  protected insufficientText(band: VarianceBandInsufficient): string {
    return insufficientCopy(band.days, band.weeks);
  }
}
