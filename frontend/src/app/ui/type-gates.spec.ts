import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';
import { StyleRule, styleRules, withChartChrome } from './testing/style-rules';

/**
 * Spec v240 §2 and §11, two source gates over every style rule in src/
 * (allSources(): .ts styles: literals and .css files; specs and styles/
 * are out):
 *
 * - tabular: Jost is proportional, so a rule that reads --font-num or
 *   --font-mono, or styles a .num cell, sets
 *   `font-variant-numeric: tabular-nums` (index Decision 4: everywhere, no
 *   exemptions; it changes only digits).
 * - faint: --text-faint is a divider colour (the corrected spec §1), so no
 *   rule's `color` reads it; captions and hints use --text-muted (index
 *   Decision 3). border-color, background and fill stay legal.
 *
 * Each gate starts with a pending set of today's offenders. Part 3's sweep
 * tasks remove entries by area and V240-16 deletes both sets. A pending file
 * must still offend, so the sets never hold a fixed file.
 */
const TABULAR_PENDING: ReadonlySet<string> = new Set([
  'app/shell/login/login.css',
  'app/shell/shell.css',
  'app/ui/async.ts',
  'app/ui/chip.ts',
  'app/ui/confidence-cell.ts',
  'app/ui/data-table/data-table.ts',
  'app/ui/hint.ts',
  'app/ui/panel-header.ts',
  'app/ui/plan-cell.ts',
  'app/ui/pnl-cell.ts',
  'app/ui/stat-tile.ts',
  'app/ui/status-cell.ts',
  'app/workspaces/analytics/tabs/tuning.ts',
  'app/workspaces/calendar/calendar.ts',
  'app/workspaces/calendar/day/calendar-day.ts',
  'app/workspaces/calendar/day/day-trade-card.ts',
  'app/workspaces/calendar/day/trade-sparkline.ts',
  'app/workspaces/cancels/cancels-summary.ts',
  'app/workspaces/dashboard/dashboard.ts',
  'app/workspaces/dashboard/panels/market-movers.ts',
  'app/workspaces/dashboard/panels/recent-activity.ts',
  'app/workspaces/dashboard/panels/trading-performance.ts',
  'app/workspaces/dashboard/panels/watchlist-panel.ts',
  'app/workspaces/gallery/gallery.ts',
  'app/workspaces/guide/guide.ts',
  'app/workspaces/plans/plan-detail.ts',
  'app/workspaces/reports/gates-tab.ts',
  'app/workspaces/research/research.ts',
  'app/workspaces/risk/risk.ts',
  'app/workspaces/system/logs-tab.ts',
  'app/workspaces/system/scan-tab.ts',
  'app/workspaces/system/settings-tab.ts',
  'app/workspaces/trades/trade-detail.ts',
  'app/workspaces/trades/trades.ts',
  'app/workspaces/versions/versions.ts',
  'app/workspaces/watchlist/earnings-calendar.ts',
  'app/workspaces/watchlist/ticker-detail.ts',
  'app/workspaces/watchlist/watchlist.ts',
  'styles.css',
]);

const FAINT_PENDING: ReadonlySet<string> = new Set([
  'app/shell/breadcrumb.ts',
  'app/ui/age-hint.ts',
  'app/ui/bar-list.ts',
  'app/ui/button.ts',
  'app/ui/column-picker.ts',
  'app/ui/direction-arrow.ts',
  'app/ui/freshness.ts',
  'app/ui/market-value.ts',
  'app/ui/matrix.ts',
  'app/ui/metric-chip.ts',
  'app/ui/plan-cell.ts',
  'app/ui/pnl-basis.ts',
  'app/ui/share-bar.ts',
  'app/ui/status-cell.ts',
  'app/workspaces/analytics/tabs/benchmark.ts',
  'app/workspaces/analytics/tabs/execution.ts',
  'app/workspaces/analytics/tabs/override-fidelity-panel.ts',
  'app/workspaces/analytics/tabs/overview.ts',
  'app/workspaces/analytics/tabs/partials.ts',
  'app/workspaces/analytics/tabs/pipeline.ts',
  'app/workspaces/analytics/tabs/runner-endings.ts',
  'app/workspaces/analytics/tabs/variance-band-panel.ts',
  'app/workspaces/calendar/calendar.ts',
  'app/workspaces/cancels/cancels-summary.ts',
  'app/workspaces/dashboard/dashboard.ts',
  'app/workspaces/dashboard/panels/equity-candles.ts',
  'app/workspaces/dashboard/panels/exposure-by-horizon.ts',
  'app/workspaces/dashboard/panels/market-movers.ts',
  'app/workspaces/dashboard/panels/recent-activity.ts',
  'app/workspaces/dashboard/panels/watchlist-panel.ts',
  'app/workspaces/guide/guide.ts',
  'app/workspaces/plans/plan-detail.ts',
  'app/workspaces/reports/attribution-tab.ts',
  'app/workspaces/reports/gates-tab.ts',
  'app/workspaces/reports/reports.ts',
  'app/workspaces/research/research.ts',
  'app/workspaces/risk/risk.ts',
  'app/workspaces/system/logs-tab.ts',
  'app/workspaces/system/scan-tab.ts',
  'app/workspaces/system/settings-tab.ts',
  'app/workspaces/trades/trade-detail.ts',
  'app/workspaces/trades/trades.ts',
  'app/workspaces/trades/why/outcome-path.ts',
  'app/workspaces/versions/versions.ts',
  'app/workspaces/watchlist/earnings-calendar.ts',
  'app/workspaces/watchlist/watchlist.ts',
]);

/* A numeric face, with or without a var() fallback:
 * `var(--font-mono, monospace)` (calendar.ts .trade-id) counts too. */
const NUM_FACE = /var\(--font-(?:num|mono)\s*(?:,[^)]*)?\)/;
const NUM_CELL = /\.num(?![\w-])/;
const TABULAR = /font-variant-numeric:[^;]*tabular-nums/;
const FAINT_TEXT = /(?:^|[\s;{])color\s*:[^;]*var\(--text-faint\)/;

type Gate = {
  id: string;
  rule: string;
  pending: ReadonlySet<string>;
  offends: (rule: StyleRule) => boolean;
};

const GATES: Gate[] = [
  {
    id: 'tabular',
    rule: 'sets tabular-nums on every --font-num, --font-mono and .num rule',
    pending: TABULAR_PENDING,
    offends: (rule) => (NUM_FACE.test(rule.body) || NUM_CELL.test(rule.selector)) && !TABULAR.test(rule.body),
  },
  {
    id: 'faint',
    rule: 'paints no text in --text-faint',
    pending: FAINT_PENDING,
    offends: (rule) => FAINT_TEXT.test(rule.body),
  },
];

/** Every source's style rules, with CHART_CHROME interpolations resolved. */
const SOURCES = allSources().map(({ name, source }) => ({
  name,
  source,
  rules: styleRules(name, withChartChrome(source)),
}));

const offenders = (gate: Gate, rules: StyleRule[]) => rules.filter(gate.offends).map((rule) => rule.selector);

describe('v240 type gates: the predicates', () => {
  const [tabular, faint] = GATES;
  const rules = (css: string) => styleRules('a.css', css);

  it('tabular flags a numeric face or a .num cell without tabular-nums', () => {
    expect(offenders(tabular, rules('.a { font-family: var(--font-num); }'))).toEqual(['.a']);
    expect(offenders(tabular, rules('.b { font-family: var(--font-mono); }'))).toEqual(['.b']);
    expect(offenders(tabular, rules('td.num { text-align: right; }'))).toEqual(['td.num']);
  });

  it('tabular sees a numeric face behind a var() fallback', () => {
    expect(offenders(tabular, rules('.d { font-family: var(--font-mono, monospace); }'))).toEqual(['.d']);
    expect(offenders(tabular, rules('.e { font-family: var(--font-num , ui-monospace, monospace); }'))).toEqual(['.e']);
    expect(offenders(tabular, rules('.f { font-family: var(--font-mono, monospace); font-variant-numeric: tabular-nums; }'))).toEqual([]);
    expect(offenders(tabular, rules('.g { font-family: var(--font-numeric, monospace); }'))).toEqual([]);
  });

  it('tabular passes the same rules with tabular-nums, and ignores .number and .num-x', () => {
    expect(offenders(tabular, rules('.a { font-family: var(--font-num); font-variant-numeric: tabular-nums; }'))).toEqual([]);
    expect(offenders(tabular, rules('.number { gap: 0; } .num-x { gap: 0; } .c { font-family: var(--font-sans); }'))).toEqual([]);
  });

  it('faint flags color but not border-color, background or fill', () => {
    expect(offenders(faint, rules('.a { color: var(--text-faint); }'))).toEqual(['.a']);
    expect(offenders(faint, rules('.b{gap:0;color:var(--text-faint)}'))).toEqual(['.b']);
    const legal = '.c { border-color: var(--text-faint); background: var(--text-faint); fill: var(--text-faint); }';
    expect(offenders(faint, rules(legal))).toEqual([]);
  });
});

for (const gate of GATES) {
  describe(`v240 type gate: ${gate.id}`, () => {
    for (const { name, rules } of SOURCES) {
      if (gate.pending.has(name)) {
        it(`${name} is pending and still offends (a sweep removes it)`, () => {
          expect(offenders(gate, rules)).not.toEqual([]);
        });
      } else {
        it(`${name} ${gate.rule}`, () => {
          expect(offenders(gate, rules)).toEqual([]);
        });
      }
    }

    it('names only scanned files in its pending set', () => {
      const scanned = new Set(SOURCES.map(({ name }) => name));
      expect([...gate.pending].filter((name) => !scanned.has(name))).toEqual([]);
    });
  });
}

describe('v240 type gates: nothing hides from them', () => {
  /* The seven chart components whose styles interpolate CHART_CHROME. */
  const INTERPOLATED = [
    'app/ui/bar-list.ts',
    'app/ui/chart-tooltip.ts',
    'app/ui/dot-plot.ts',
    'app/ui/histogram.ts',
    'app/ui/line-chart.ts',
    'app/ui/strip-plot.ts',
    'app/ui/waterfall.ts',
  ];
  const holdsExpr = (rules: StyleRule[]) => rules.some((rule) => `${rule.selector} ${rule.body}`.includes('__expr__'));

  it('pins the files whose style rules interpolate, read raw', () => {
    const raw = SOURCES.filter(({ name, source }) => holdsExpr(styleRules(name, source))).map(({ name }) => name);
    expect(raw).toEqual(INTERPOLATED);
  });

  it('leaves no interpolation in any rule once CHART_CHROME is substituted', () => {
    expect(SOURCES.filter(({ rules }) => holdsExpr(rules)).map(({ name }) => name)).toEqual([]);
  });

  const INLINE_FAINT = /(?:^|[\s;{"'])color\s*:\s*var\(--text-faint\)/g;
  const BOUND_FAINT = /\[style\.color\]\s*=\s*"[^"]*--text-faint/;
  const count = (text: string) => (text.match(INLINE_FAINT) ?? []).length;

  for (const { name, source, rules } of SOURCES) {
    it(`${name} paints no template or inline text in --text-faint`, () => {
      const code = stripComments(source);
      const inRules = rules.reduce((n, rule) => n + count(` ${rule.body}`), 0);
      expect(count(code)).toBe(inRules);
      expect(code).not.toMatch(BOUND_FAINT);
    });
  }
});
