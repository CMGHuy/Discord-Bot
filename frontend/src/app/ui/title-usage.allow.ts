/**
 * v194 A3 -- every native `title` left in `src/app`, classified once.
 *
 * A `title` only answers a mouse hover: a phone, a keyboard and a screen
 * reader never see it. So a `title` may only carry what is said elsewhere
 * too (`echo`) or name an icon-only control (`control-name`, beside an
 * `aria-label`). Anything that explains -- a definition, a caveat, why a
 * value is absent -- is an `sb-hint` or visible text instead.
 * `explanation-pending` marks the sites a later v194 task converts; it is
 * empty once V194-15b lands, and `title-usage.spec.ts` fails on any
 * `title` binding not listed here.
 *
 * `binding` is the attribute exactly as written (whitespace runs collapsed
 * to one space); `file` is relative to `src/app`.
 */
export interface TitleSite {
  file: string;
  binding: string;
  kind: 'echo' | 'control-name' | 'explanation-pending';
  note: string;
}

/** Elements whose `title` is a component input rendering visible heading
 *  text, not a tooltip. */
export const TITLE_INPUT_ELEMENTS: readonly string[] = ['sb-panel-header', 'sb-empty-state', 'sb-confirm-dialog'];

const FRAGILE = 'title="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it."';

export const TITLE_ALLOW: readonly TitleSite[] = [
  // -- shell ---------------------------------------------------------------
  { file: 'shell/connection-status.ts', binding: '[title]="hint()"', kind: 'control-name', note: 'status dot; aria-label carries the state word, panels carry data age' },
  { file: 'shell/profile-menu.ts', binding: '[attr.title]="haloTitle()"', kind: 'control-name', note: 'the avatar menu button: bot up/down beside its aria-label' },
  { file: 'shell/tape/tape.ts', binding: "[attr.title]=\"asOfTime() === ABSENT ? null : 'Tape data as of ' + asOfTime()\"", kind: 'echo', note: 'as-of time; each tile shows its own age' },
  { file: 'shell/tape/tape.ts', binding: 'title="Yahoo had no value; an ETF tracking this index stands in. Change only, never the ETF\'s price."', kind: 'explanation-pending', note: 'V194-14b: proxy caveat' },
  // -- ui primitives ---------------------------------------------------------
  { file: 'ui/age-hint.ts', binding: "[attr.title]=\"'Price is ' + t.replace(' ago', '') + ' old'\"", kind: 'echo', note: 'restates the visible age' },
  { file: 'ui/bar-list.ts', binding: '[title]="row.label"', kind: 'echo', note: 'full text of a truncated bar label' },
  { file: 'ui/direction-arrow.ts', binding: '[title]="text"', kind: 'control-name', note: 'glyph name, same as its aria-label' },
  { file: 'ui/icon.ts', binding: "'[attr.title]': 'tip()'", kind: 'control-name', note: 'names an icon' },
  { file: 'ui/layout.ts', binding: "'[attr.title]': 'description()'", kind: 'explanation-pending', note: 'V194-14b: sb-panel description; the header sb-hint already says it' },
  { file: 'ui/layout.ts', binding: '[attr.title]="tab.icon ? tab.label : null"', kind: 'control-name', note: 'icon-only tab, beside its aria-label' },
  { file: 'ui/matrix.ts', binding: '[attr.title]="cellTitle(row, col, r, c)"', kind: 'echo', note: 'row, column and value the cell colour encodes' },
  { file: 'ui/metric-card.ts', binding: "'[attr.title]': 'description()'", kind: 'explanation-pending', note: 'V194-14b: card definition' },
  { file: 'ui/plan-cell.ts', binding: '[title]="planTooltip"', kind: 'explanation-pending', note: 'V194-14b: runner line 1 definition' },
  { file: 'ui/plan-cell.ts', binding: '[title]="trailTooltip()"', kind: 'explanation-pending', note: 'V194-14b: runner line 2 definition and caveats' },
  { file: 'ui/plan-cell.ts', binding: '[title]="tooltip()"', kind: 'echo', note: 'the levels the trade detail plan card shows, spelled out' },
  { file: 'ui/stat-tile.ts', binding: '[title]="sampleTitle()"', kind: 'explanation-pending', note: 'V194-14b: thin-sample shortfall' },
  { file: 'ui/status-cell.ts', binding: 'title="P&L if the trailing stop is hit"', kind: 'explanation-pending', note: 'V194-14b: bar end definition' },
  { file: 'ui/status-cell.ts', binding: '[title]="row().status_label"', kind: 'echo', note: 'the status label the cell prints' },
  { file: 'ui/status-cell.ts', binding: 'title="P&L at the best price since TP1"', kind: 'explanation-pending', note: 'V194-14b: bar end definition' },
  { file: 'ui/status-cell.ts', binding: 'title="This position\'s price could not be freshly fetched -- the number shown may be delayed."', kind: 'explanation-pending', note: 'V194-14b: stale-price caveat' },
  // -- calendar --------------------------------------------------------------
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[attr.title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: Total tile, R definition' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[attr.title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: Average trade tile' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[attr.title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: Worst drawdown tile' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: month-to-date R' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: breakdown R column head' },
  { file: 'workspaces/calendar/day/calendar-day.ts', binding: '[attr.title]="breakdownWinRate(row) === absent ? winNote : null"', kind: 'explanation-pending', note: 'V194-15: why win % is withheld' },
  { file: 'workspaces/calendar/day/day-trade-card.ts', binding: '[title]="rTooltip"', kind: 'explanation-pending', note: 'V194-15: R definition' },
  { file: 'workspaces/calendar/day/trade-sparkline.ts', binding: 'title="No cached daily bars for this row"', kind: 'explanation-pending', note: 'V194-15: why the sparkline is absent' },
  // -- cancels / dashboard ---------------------------------------------------
  { file: 'workspaces/cancels/cancels-summary.ts', binding: 'title="Fewer than {{ data().small_n_threshold }} resolved plans: an anecdote, not a rate"', kind: 'explanation-pending', note: 'V194-15b: small-N caveat' },
  { file: 'workspaces/dashboard/dashboard.ts', binding: '[title]="openTitle"', kind: 'explanation-pending', note: 'V194-15: share still open on a PARTIAL row' },
  { file: 'workspaces/dashboard/dashboard.ts', binding: 'title="Trailing stop"', kind: 'control-name', note: 'names the trailing-stop icon' },
  { file: 'workspaces/dashboard/dashboard.ts', binding: 'title="Live P&L, then projected P&L at target and at stop"', kind: 'explanation-pending', note: 'V194-15: P&L cell reading order' },
  { file: 'workspaces/dashboard/dashboard.ts', binding: 'title="Projected R if price reaches target"', kind: 'explanation-pending', note: 'V194-15: expected R definition' },
  { file: 'workspaces/dashboard/panels/equity-candles.ts', binding: '[attr.title]="isChangePart(part.text) ? changeTooltip : null"', kind: 'explanation-pending', note: 'V194-15: change is not a return on capital' },
  { file: 'workspaces/dashboard/panels/equity-candles.ts', binding: 'title="Back to today: chart and figures"', kind: 'control-name', note: 'reset button, beside its aria-label' },
  { file: 'workspaces/dashboard/panels/recent-activity.ts', binding: '[title]="statusLabel(event)"', kind: 'control-name', note: 'status icon, beside its aria-label' },
  { file: 'workspaces/dashboard/trade-drawer.ts', binding: 'title="The bot places no orders: every trade on this page is a paper trade."', kind: 'explanation-pending', note: 'V194-15: paper-trade caveat' },
  // -- research / system -----------------------------------------------------
  { file: 'workspaces/research/research.ts', binding: '[attr.title]="row.hypothesis"', kind: 'echo', note: 'full text of a truncated hypothesis' },
  { file: 'workspaces/system/settings-tab.ts', binding: 'title="Default value"', kind: 'echo', note: 'names the default badge the row prints' },
  { file: 'workspaces/system/settings-tab.ts', binding: 'title="Restart required to take effect"', kind: 'explanation-pending', note: 'V194-15b: restart caveat' },
  { file: 'workspaces/system/settings-tab.ts', binding: "[title]=\"'Reset to ' + field.default\"", kind: 'echo', note: 'the default the badge beside it shows' },
  { file: 'workspaces/system/swallowed-errors-panel.ts', binding: '[attr.title]="line.lastSeenAt"', kind: 'echo', note: 'exact timestamp of the relative time shown' },
  // -- trades ----------------------------------------------------------------
  { file: 'workspaces/trades/position-card.ts', binding: FRAGILE, kind: 'explanation-pending', note: 'V194-15: gap-fragile stop caveat' },
  { file: 'workspaces/trades/trade-detail.ts', binding: '[title]="cohortTooltip()"', kind: 'explanation-pending', note: 'V194-15: cohort chip meaning' },
  { file: 'workspaces/trades/trade-detail.ts', binding: "[title]=\"'Trade ID: ' + trade.id\"", kind: 'echo', note: 'the id printed beside it' },
  { file: 'workspaces/trades/trades.ts', binding: 'title="Downloads the entire trade log. The filters above do not narrow it."', kind: 'explanation-pending', note: 'V194-15: export scope caveat' },
  { file: 'workspaces/trades/trades.ts', binding: '[title]="openTitle"', kind: 'explanation-pending', note: 'V194-15: share still open on a PARTIAL row' },
  { file: 'workspaces/trades/trades.ts', binding: 'title="Trailing stop"', kind: 'control-name', note: 'names the trailing-stop icon' },
  { file: 'workspaces/trades/why/sizing-panel.ts', binding: FRAGILE, kind: 'explanation-pending', note: 'V194-15: gap-fragile stop caveat' },
  { file: 'workspaces/trades/why/why-panel.ts', binding: 'title="no data — neutral points awarded"', kind: 'explanation-pending', note: 'V194-15: unevaluated factor' },
  { file: 'workspaces/trades/why/why-panel.ts', binding: 'title="off in current config"', kind: 'explanation-pending', note: 'V194-15: gate switched off' },
  // -- versions / watchlist --------------------------------------------------
  { file: 'workspaces/versions/versions.ts', binding: "[attr.title]=\"component + ' ' + version + ' — click to filter'\"", kind: 'control-name', note: 'filter chip button: names what a click does' },
  { file: 'workspaces/versions/versions.ts', binding: 'title="This component did not exist yet"', kind: 'explanation-pending', note: 'V194-15b: hatched lane segment' },
  { file: 'workspaces/versions/versions.ts', binding: 'title="The releases listed below"', kind: 'explanation-pending', note: 'V194-15b: bracket under the lanes' },
  { file: 'workspaces/watchlist/watchlist.ts', binding: 'title="Alpaca missed this quote; yfinance answered instead"', kind: 'explanation-pending', note: 'V194-15b: fallback badge' },
];

/** Sites a later v194 task converts. Empty once V194-15b lands. */
export const TITLE_PENDING: readonly TitleSite[] = TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending');
