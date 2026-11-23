import { describe, expect, it } from 'vitest';

import { allSources, stripComments } from './testing/all-sources';

/**
 * v241 (spec v240 §4): the standalone marker glyphs that sb-icon replaced.
 * A text glyph changes shape with the font and sits off the baseline; the
 * icons do not. Each row matches one spelling: the character, its HTML
 * character reference (decimal or hex), its JS or CSS escape, and the close
 * `×` standing alone in an element or a string.
 *
 * Not here on purpose (index Decision 4): a glyph inside a value or a
 * sentence stays text -- `1.40×`, `1.5 × ATR`, `×{{ throttle }}`, `→`,
 * plan-cell's banked-target `✓`, the server-built `⚠ SQUEEZE RISK` prefix.
 */
type ReplacedGlyph = { name: string; pattern: RegExp };

const REPLACED_GLYPHS: readonly ReplacedGlyph[] = [
  { name: 'a marker glyph (ⓘ ▲ ▼ ▾ ▸ ◉ ○)', pattern: /[ⓘ▲▼▾▸◉○]/u },
  { name: 'a marker glyph as a decimal reference', pattern: /&#0*(?:9432|9650|9660|9662|9656|9673|9675);/ },
  { name: 'a marker glyph as a hex reference', pattern: /&#x0*(?:24d8|25b2|25bc|25be|25b8|25c9|25cb);/i },
  { name: 'a marker glyph as a JS or CSS escape', pattern: /\\(?:u\{?)?0*(?:24d8|25b2|25bc|25be|25b8|25c9|25cb)(?![0-9a-f])/i },
  { name: 'a close × alone in an element', pattern: />\s*(?:×|&times;|&#215;|&#xd7;)\s*</i },
  { name: 'a close × alone in a string', pattern: /(['"`])\s*(?:×|&times;|\\u00d7|\\d7)\s*\1/i },
];

/** The REPLACED_GLYPHS rows a piece of source text offends. */
function offences(text: string): string[] {
  return REPLACED_GLYPHS.filter(({ pattern }) => pattern.test(text)).map(({ name }) => name);
}

/**
 * Spec v240 §4 correction: the controls whose glyph became an icon, or that
 * hold an icon beside their name. Each pattern pins the control's accessible
 * name on the control itself and, where the icon sits inside it, the icon's
 * empty title (no tooltip, no second name: never "Close Close").
 */
type GuardedSite = { control: string; file: string; names: RegExp };

const GUARDED_SITES: readonly GuardedSite[] = [
  {
    control: 'direction arrow',
    file: 'app/ui/direction-arrow.ts',
    names: /<span class="arrow"[^>]*role="img"[^>]*\[attr\.aria-label\]="text"[^>]*>\s*<sb-icon \[name\]="icon\(\)" title="" \/>/,
  },
  {
    control: 'recent-activity status icon (named on its own host)',
    file: 'app/workspaces/dashboard/panels/recent-activity.ts',
    names: /<sb-icon \[name\]="icon\(event\)"[^>]*\[attr\.aria-label\]="statusLabel\(event\)"/,
  },
  {
    control: 'plan-cell closed icon (named on the price beside it)',
    file: 'app/ui/plan-cell.ts',
    names: /<sb-icon name="closed" class="closed-icon"[^>]*\/>[\s\S]{0,120}?<span class="closed" \[attr\.aria-label\]="'Closed out at ' \+ fmt\(closedAt\(\)\)"/,
  },
  {
    control: 'watchlist tape toggle',
    file: 'app/workspaces/watchlist/watchlist.ts',
    names: /class="tape-toggle"[^>]*\[attr\.aria-pressed\]="tape\.symbols\(\)\.includes\(row\.symbol\)"[^>]*\[attr\.aria-label\]="'Show ' \+ row\.symbol \+ ' in the live tape'"[^>]*>\s*<sb-icon [^>]*title="" \/>\s*<\/button>/,
  },
  {
    control: 'drawer close button',
    file: 'app/ui/layout.ts',
    names: /<button type="button" class="close" aria-label="Close" \(click\)="requestClose\(\)">\s*<sb-icon name="close" title="" \/>\s*<\/button>/,
  },
  {
    control: 'panel collapse toggle',
    file: 'app/ui/layout.ts',
    names: /class="panel-toggle"[^>]*\[attr\.aria-label\]="\(expanded\(\) \? 'Collapse ' : 'Expand '\) \+ text"[^>]*>\s*<sb-icon \[name\]="expanded\(\) \? 'down' : 'expand'" title="" \/>/,
  },
  {
    control: 'data-table row-detail toggle',
    file: 'app/ui/data-table/data-table.ts',
    names: /class="expander detail-toggle"[^>]*\[attr\.aria-label\]="\(isExpanded\(row\) \? 'Show less for ' : 'Show more for '\) \+ rowLabel\(row\)"[^>]*>\s*<sb-icon \[name\]="isExpanded\(row\) \? 'down' : 'expand'" title="" \/>/,
  },
  {
    control: 'info trigger (sb-hint)',
    file: 'app/ui/hint.ts',
    names: /class="trigger"[^>]*\[attr\.aria-label\]="label\(\)"[^>]*>\s*<sb-icon name="info" title="" \/>/,
  },
];

const SOURCES = allSources();

describe('replaced glyphs stay replaced (v241, spec v240 §4)', () => {
  // The patterns first: a gate that matches nothing passes everything.
  it.each([
    "{{ open ? '▾' : '▸' }}",
    '{{ store.lastDate() }} &#9650; now',
    '&#x25B2;',
    '&#x25b8;',
    "content: '\\25B8'",
    "'\\u25BC'",
    "'\\u{25C9}'",
    'ⓘ',
    "{{ on ? '◉' : '○' }}",
    '(click)="requestClose()">×</button>',
    '<button> &times; </button>',
    "content: '×'",
    '"\\u00d7"',
  ])('catches %s', (text) => {
    expect(offences(text)).not.toEqual([]);
  });

  it.each([
    '1.40×',
    '1.5 × ATR',
    'Drawdown throttle at ×{{ fmt(store.throttleMultiplier()) }}',
    'shares × stop',
    '115.26 → 123.05',
    '`${fmt} ✓`',
    "line.startsWith('⚠')",
    '#9650 is a number, not a reference',
    "content: '\\25B80'",
    '',
  ])('keeps %j as text', (text) => {
    expect(offences(text)).toEqual([]);
  });

  it('finds none in any template, stylesheet or component', () => {
    const found = SOURCES.flatMap(({ name, source }) =>
      offences(stripComments(source)).map((offence) => `${name}: ${offence}`));
    expect(found).toEqual([]);
  });

  it('really scans the sources it guards', () => {
    // An empty or misrooted scan would pass the test above vacuously.
    const names = new Set(SOURCES.map(({ name }) => name));
    expect(names.size).toBeGreaterThan(100);
    for (const file of [...GUARDED_SITES.map((site) => site.file), 'app/workspaces/versions/versions.ts', 'app/workspaces/guide/guide.ts']) {
      expect(names.has(file), file).toBe(true);
    }
  });
});

describe('every swapped control keeps its accessible name (v241, spec v240 §4 correction)', () => {
  it.each(GUARDED_SITES.map((site) => [site.control, site] as const))('%s', (_control, site) => {
    const source = SOURCES.find(({ name }) => name === site.file)?.source;
    expect(source, site.file).toBeDefined();
    expect(stripComments(source!)).toMatch(site.names);
  });

  it('guards each control the spec names, once', () => {
    const controls = GUARDED_SITES.map((site) => site.control);
    expect(new Set(controls).size).toBe(controls.length);
    expect(controls).toHaveLength(8);
  });
});
