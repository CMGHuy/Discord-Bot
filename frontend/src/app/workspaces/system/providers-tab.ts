import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

import { DataSourcesHealth } from '../../api/models';
import { SystemStore } from '../../stores/system.store';
import { num } from '../../ui/format';
import { Panel } from '../../ui/layout';
import { Sparkline } from '../../ui/sparkline';
import { ProviderHealthPanel } from './provider-health-panel';
import { SwallowedErrorsPanel } from './swallowed-errors-panel';

/** v106: "Alpaca · IEX" when Alpaca serves the live path, else the plain
 *  pre-v106 source. Moved from risk.ts with its panel (v195 §5.1). */
export function dataSourceName(ds: DataSourcesHealth): string {
  return ds.enabled ? `Alpaca · ${ds.feed.toUpperCase()}` : 'yfinance only';
}

/** How often the live path fell back to yfinance, over how many scans. */
export function fallbackText(ds: DataSourcesHealth): string {
  if (ds.fallback_rate === null) return `no Alpaca traffic yet (${ds.scans} scans)`;
  return `${(ds.fallback_rate * 100).toFixed(1)}% fallback (${ds.scans} scans)`;
}

/** The last scan's duration. An unknown one is the bare em dash: a unit
 *  after "no value" (Risk printed `—s`) reads like a measurement. */
export function scanSecondsText(seconds: number | null): string {
  return seconds === null ? num(null) : `${num(seconds, 1)}s`;
}

/**
 * System → Providers (v195 §5.1): where the data comes from and whether the
 * scanner is keeping up. Four panels, one question -- "can I trust what the
 * other pages show right now?":
 *
 * - *Data providers* and *Swallowed errors* (v148, `GET /system/health`),
 *   reused as they were on the Scan tab.
 * - *Data source* and *Scan health* (v106, the `scan_health` block of
 *   `GET /risk`), moved from Risk, which now shows only risk. The freshness
 *   chip in the top bar (V195-17) carries the one figure that must stay
 *   visible everywhere; this tab is the detail behind it.
 *
 * Each read fails on its own: a failed `/risk` keeps the provider rows and
 * says which read is stale, and the reverse.
 */
@Component({
  selector: 'sb-providers-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Sparkline, ProviderHealthPanel, SwallowedErrorsPanel],
  template: `
    <sb-provider-health-panel [health]="store.health()" />

    <!-- v106: where live bars and prices come from, and how often Alpaca
         misses. A fallback price is still a real price, so the rate is
         information; an open breaker is the caution -- every eligible
         symbol is on yfinance until it closes. -->
    <sb-panel heading="Data source">
      @if (store.dataSources(); as ds) {
        <div class="sources" [class.warn]="ds.breaker_open">
          <span class="source-name">{{ sourceName(ds) }}</span>
          @if (ds.enabled) {
            <span class="source-rate num">{{ fallback(ds) }}</span>
          }
        </div>
        @if (ds.enabled && ds.breaker_open) {
          <p class="note warn">
            Alpaca breaker open — live prices are coming from yfinance until it closes.
          </p>
        }
      } @else {
        <p class="none">No data-source reading yet.</p>
      }
    </sb-panel>

    <sb-panel heading="Scan health">
      <div class="scan">
        <div class="scan-figures">
          <span class="scan-latest num">{{ seconds(store.scanLatestS()) }}</span>
          <span class="scan-label">last scan</span>
        </div>
        @if (store.scanDurations().length) {
          <sb-sparkline
            [points]="store.scanDurations()"
            label="Recent scan durations, in seconds"
          />
        }
      </div>
      @if (store.scanSlowdown()) {
        <!-- Amber, not red: a slow scan is a caution about freshness, not a
             loss. It matters because stale scans mean every figure on the
             other pages is older than it looks. -->
        <p class="note warn">
          Scans are running slower than usual — setups and prices may be stale.
        </p>
      }
    </sb-panel>

    <sb-swallowed-errors-panel [health]="store.health()" />

    @if (store.healthError(); as message) {
      <p class="error" role="alert">Data providers and swallowed errors: {{ message }}</p>
    }
    @if (store.riskError(); as message) {
      <p class="error" role="alert">Scan health and data source: {{ message }}</p>
    }
  `,
  styles: `
    /* minmax(0, 1fr), not the implicit auto track: one un-shrinkable panel
       must not stretch the tab past the viewport (the Scan tab's rule).
       No backticks in here: these styles live in a TS template literal. */
    :host { display: grid; grid-template-columns: minmax(0, 1fr); gap: var(--section-gap); }

    /* -- data source (v106, moved from risk.ts) -- */
    .sources { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
    .source-name { font-weight: 600; }
    .source-rate { color: var(--text-secondary); font-size: var(--text-table); }
    .sources.warn .source-name { color: var(--warn); }

    /* -- scan health (moved from risk.ts) -- */
    .scan { display: flex; align-items: center; gap: var(--register-pad); }
    .scan-figures { display: flex; align-items: baseline; gap: var(--space-6); }
    .scan-latest { font-size: var(--text-subhead); font-weight: 600; }
    /* --text-micro: an eyebrow caption, uppercase is kept for micro labels only (spec §1.3). */
    .scan-label {
      color: var(--text-muted);
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .scan sb-sparkline { flex: 1 1 auto; min-width: 80px; max-width: 320px; }

    /* p.note, not bare .note: primitives.spec reserves the bare class for a promoted composite. */
    p.note { margin-top: var(--space-8); color: var(--text-secondary); font-size: var(--text-table); }
    .warn { color: var(--warn); }
    .none { color: var(--text-muted); font-size: var(--text-table); }
    .error { color: var(--neg); font-size: var(--text-table); }
  `,
})
export class ProvidersTab {
  protected readonly store = inject(SystemStore);

  protected readonly sourceName = dataSourceName;
  protected readonly fallback = fallbackText;
  protected readonly seconds = scanSecondsText;
}
