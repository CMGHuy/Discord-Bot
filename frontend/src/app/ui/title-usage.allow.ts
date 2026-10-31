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

export const TITLE_ALLOW: readonly TitleSite[] = [
  // -- shell ---------------------------------------------------------------
  { file: 'shell/connection-status.ts', binding: '[title]="hint()"', kind: 'control-name', note: 'status dot; aria-label carries the state word, panels carry data age' },
  { file: 'shell/profile-menu.ts', binding: '[attr.title]="haloTitle()"', kind: 'control-name', note: 'the avatar menu button: bot up/down beside its aria-label' },
  { file: 'shell/tape/tape.ts', binding: "[attr.title]=\"asOfTime() === ABSENT ? null : 'Tape data as of ' + asOfTime()\"", kind: 'echo', note: 'as-of time; each tile shows its own age' },
  // -- ui primitives ---------------------------------------------------------
  { file: 'ui/age-hint.ts', binding: "[attr.title]=\"'Price is ' + t.replace(' ago', '') + ' old'\"", kind: 'echo', note: 'restates the visible age' },
  { file: 'ui/bar-list.ts', binding: '[title]="row.label"', kind: 'echo', note: 'full text of a truncated bar label' },
  { file: 'ui/direction-arrow.ts', binding: '[title]="text"', kind: 'control-name', note: 'glyph name, same as its aria-label' },
  { file: 'ui/icon.ts', binding: "'[attr.title]': 'tip()'", kind: 'control-name', note: 'names an icon' },
  { file: 'ui/layout.ts', binding: '[attr.title]="tab.icon ? tab.label : null"', kind: 'control-name', note: 'icon-only tab, beside its aria-label' },
  { file: 'ui/matrix.ts', binding: '[attr.title]="cellTitle(row, col, r, c)"', kind: 'echo', note: 'row, column and value the cell colour encodes' },
  { file: 'ui/plan-cell.ts', binding: '[title]="tooltip()"', kind: 'echo', note: 'the levels the trade detail plan card shows, spelled out' },
  { file: 'ui/status-cell.ts', binding: '[title]="row().status_label"', kind: 'echo', note: 'the status label the cell prints' },
  // -- calendar --------------------------------------------------------------
  // -- cancels / dashboard ---------------------------------------------------
  { file: 'workspaces/dashboard/dashboard.ts', binding: 'title="Trailing stop"', kind: 'control-name', note: 'names the trailing-stop icon' },
  { file: 'workspaces/dashboard/panels/equity-candles.ts', binding: 'title="Back to today: chart and figures"', kind: 'control-name', note: 'reset button, beside its aria-label' },
  { file: 'workspaces/dashboard/panels/recent-activity.ts', binding: '[title]="statusLabel(event)"', kind: 'control-name', note: 'status icon, beside its aria-label' },
  // -- research / system -----------------------------------------------------
  { file: 'workspaces/research/research.ts', binding: '[attr.title]="row.hypothesis"', kind: 'echo', note: 'full text of a truncated hypothesis' },
  { file: 'workspaces/system/settings-tab.ts', binding: 'title="Default value"', kind: 'echo', note: 'names the default badge the row prints' },
  { file: 'workspaces/system/settings-tab.ts', binding: "[title]=\"'Reset to ' + field.default\"", kind: 'echo', note: 'the default the badge beside it shows' },
  { file: 'workspaces/system/swallowed-errors-panel.ts', binding: '[attr.title]="line.lastSeenAt"', kind: 'echo', note: 'exact timestamp of the relative time shown' },
  // -- trades ----------------------------------------------------------------
  { file: 'workspaces/trades/trade-detail.ts', binding: "[title]=\"'Trade ID: ' + trade.id\"", kind: 'echo', note: 'the id printed beside it' },
  { file: 'workspaces/trades/trades.ts', binding: 'title="Trailing stop"', kind: 'control-name', note: 'names the trailing-stop icon' },
  // -- versions / watchlist --------------------------------------------------
  { file: 'workspaces/versions/versions.ts', binding: "[attr.title]=\"component + ' ' + version + ' — click to filter'\"", kind: 'control-name', note: 'filter chip button: names what a click does' },
];

/** Sites a later v194 task converts. Empty once V194-15b lands. */
export const TITLE_PENDING: readonly TitleSite[] = TITLE_ALLOW.filter((s) => s.kind === 'explanation-pending');
