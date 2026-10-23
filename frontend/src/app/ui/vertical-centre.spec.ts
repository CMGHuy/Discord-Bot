import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * The vertical-centre rules (docs/claude/ui-design.md § Checklist): a table
 * row's figures share one line, an icon sits on the centre of its text.
 * jsdom does no layout, so these pin the stylesheet rules that make it so;
 * the geometry itself is the layout audit's vcenter check
 * (frontend/scripts/layout-audit.mjs). Stylesheets are read from disk for
 * the reason tokens.spec.ts gives.
 */
const read = (path: string) => readFileSync(join(process.cwd(), path), 'utf8');
/** The body of the first rule whose selector is exactly `selector`. */
function rule(source: string, selector: string): string {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  const match = new RegExp(`(?:^|[\\s}])${escaped}\\s*\\{([^}]*)\\}`).exec(source);
  expect(match, `no rule for ${selector}`).not.toBeNull();
  return match![1];
}

describe('vertical centring', () => {
  it('a magnitude bar in a table cell hangs in the padding, not in the content', () => {
    // Counted as content, the 3px bar lifted the R figure ~2px above the row.
    const source = read('src/app/ui/magnitude.ts');
    expect(rule(source, ':host-context(td)')).toMatch(/margin-bottom:\s*-3px/);
    expect(rule(source, ':host')).toMatch(/height:\s*3px/); // the margin cancels exactly this height
  });

  it('a sparkline is a block box, so no baseline strut lifts it off the middle', () => {
    expect(rule(read('src/app/ui/sparkline.ts'), ':host')).toMatch(/display:\s*block/);
  });

  it('an icon set inline in text centres on that text', () => {
    const host = rule(read('src/app/ui/icon.ts'), ':host');
    expect(host).toMatch(/vertical-align:\s*middle/);
    expect(host).toMatch(/display:\s*inline-flex/);
  });

  it('the gallery numerics R cell stays on one line with its bar centred beside it', () => {
    const source = read('src/app/workspaces/gallery/gallery.ts');
    expect(rule(source, '.numerics-demo th.num, .numerics-demo td.num')).toMatch(/white-space:\s*nowrap/);
    const bar = rule(source, '.numerics-demo sb-magnitude');
    expect(bar).toMatch(/vertical-align:\s*middle/);
    expect(bar).toMatch(/margin:\s*0 0 0 /); // resets the in-cell -3px, which would skew an inline bar
  });

  it('data-table cells centre their content', () => {
    expect(rule(read('src/app/ui/data-table/data-table.ts'), 'th, td')).toMatch(/vertical-align:\s*middle/);
  });
});
