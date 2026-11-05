import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Button, type ButtonVariant } from './button';
import { allSources, stripComments } from './testing/all-sources';
import { resolveToken } from './testing/resolve-token';

@Component({
  imports: [Button],
  template: `<button sb-button [variant]="variant">Label</button>`,
})
class Host {
  variant: ButtonVariant = 'secondary';
}

function render(variant: ButtonVariant): HTMLButtonElement {
  const f = TestBed.createComponent(Host);
  f.componentInstance.variant = variant;
  f.detectChanges();
  return f.nativeElement.querySelector('button')!;
}

describe('Button variants', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  for (const variant of ['primary', 'secondary', 'danger', 'danger-quiet', 'ghost', 'icon',
                         'chip', 'segment', 'link'] as ButtonVariant[]) {
    it(`puts the ${variant} class on the native button`, () => {
      expect(render(variant).classList.contains(variant)).toBe(true);
    });
  }

  it('emits exactly one variant class, so danger-quiet is never also danger', () => {
    const el = render('danger-quiet');
    expect([...el.classList]).toEqual(['danger-quiet']);
  });

  it('paints danger-icon as icon geometry, quiet until hovered or focused', () => {
    const el = render('danger-icon');
    expect(el.classList).toContain('danger-icon');
  });

  it('keeps the element a native button so disabled and submit still work', () => {
    const el = render('chip');
    expect(el.tagName).toBe('BUTTON');
  });
});

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/button.ts'), 'utf8');
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const rule = (selector: string) =>
  SOURCE.match(new RegExp(`${esc(selector)}\\s*\\{[^}]*\\}`))?.[0] ?? '';

/* v80 D4. Asserted against the stylesheet text, as tokens.spec.ts does:
 * jsdom does not resolve var() inside a shorthand, so a computed-style
 * assertion here would be about jsdom rather than about the button. */
describe('v80 D4: the button restyle', () => {
  /* v195 §1.2: the fill is one flat tier-3 colour (--btn-fill), still set
   * through the background shorthand so no gradient can creep back as an
   * image under a background-color. */
  it('fills primary with the flat button fill and its own ink', () => {
    const primary = rule(':host(.primary)');
    expect(primary).toContain('background: var(--btn-fill)');
    expect(primary).toContain('color: var(--on-accent)');
    expect(primary).not.toContain('background-color');
  });

  it('hovers primary onto the lighter fill, not a color-mix', () => {
    const hover = rule(':host(.primary:not([disabled]):hover)');
    expect(hover).toContain('background: var(--btn-fill-hover)');
    expect(hover).not.toContain('color-mix');
  });

  it('draws secondary as a hairline, not a raised fill', () => {
    const r = rule(':host(.secondary)');
    expect(r).toContain('background: transparent');
    expect(r).toContain('border-color: var(--border-strong)');
  });

  /* v195 Phase 2, correction 6: two danger variants, so a halt never looks
   * like housekeeping. */
  it('paints danger as one solid loss-colour fill with ground ink (the killswitch)', () => {
    const danger = rule(':host(.danger)');
    expect(danger).toContain('background: var(--neg)');
    expect(danger).toContain('border-color: var(--neg)');
    expect(danger).toContain('color: var(--bg)');
    expect(danger).not.toContain('transparent');
    expect(rule(':host(.danger:not([disabled]):hover)')).toContain('filter: brightness(1.1)');
  });

  it('outlines danger-quiet in the loss colour and fills it on hover (the old danger look)', () => {
    const quiet = rule(':host(.danger-quiet)');
    expect(quiet).toContain('background: transparent');
    expect(quiet).toContain('border-color: var(--neg)');
    expect(quiet).toContain('color: var(--neg)');
    const hover = rule(':host(.danger-quiet:not([disabled]):hover)');
    expect(hover).toContain('background: var(--neg)');
    expect(hover).toContain('color: var(--bg)');
  });

  it('keeps the solid danger ink readable: --bg on --neg clears WCAG AA', () => {
    const lum = (hex: string) => {
      const ch = (i: number) => {
        const c = parseInt(hex.slice(1 + i * 2, 3 + i * 2), 16) / 255;
        return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
      };
      return 0.2126 * ch(0) + 0.7152 * ch(1) + 0.0722 * ch(2);
    };
    const [hi, lo] = [lum(resolveToken('--neg')), lum(resolveToken('--bg'))].sort((a, b) => b - a);
    expect((hi + 0.05) / (lo + 0.05)).toBeGreaterThanOrEqual(4.5);
  });

  it('grows both icon variants to a square touch target', () => {
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 1023px\) \{([\s\S]*?)\n {4}\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain(':host(.icon), :host(.danger-icon)');
    expect(block![1]).toContain('min-width: var(--control-h)');
    expect(block![1]).toContain('min-height: var(--control-h)');
  });

  it('marks segment and chip deprecated in favour of sb-segmented', () => {
    expect(SOURCE).toMatch(/Deprecated \(v80 D4\)[\s\S]*sb-segmented/);
  });
});

describe('button touch floor', () => {
  const read = (p: string) => readFileSync(join(process.cwd(), p), 'utf8');

  it.each([':host(.ghost)', ':host(.chip)', ':host(.link)'])(
    '%s keeps a one-glyph label at the --hit-min width (v179 layout audit)',
    (selector) => {
      expect(rule(selector)).toContain('min-width: var(--hit-min)');
    },
  );

  it.each([
    'src/app/ui/button.ts',
    'src/app/ui/chip.ts',
    'src/app/ui/control-bar.ts',
  ])('%s never sets min-height: 0 on an interactive host', (path) => {
    // tokens.css raises --control-h to 44px under a coarse pointer. A
    // component that sets min-height: 0 opts every one of its call sites out
    // of that floor, which is how chips reached ~28px on a phone.
    expect(read(path)).not.toMatch(/min-height:\s*0\b/);
  });
});

/* Spec v168 §3 #5. The primary gradient cannot transition (v167 §3), so
 * hover brightens it with a filter (v195 §1.2 deleted motion.css's glow); every
 * enabled button presses to .97; on touch the press also tints. */
describe('v168 #5: hover and press', () => {
  const MOTION = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8')
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/\s+/g, ' ');

  it('brightens the primary gradient on hover', () => {
    const hover = rule(':host(.primary:not([disabled]):hover)');
    expect(hover).toContain('background: var(--btn-fill-hover)');
    expect(hover).toContain('filter: brightness(1.1)');
  });

  it('presses every enabled button to .97', () => {
    expect(rule(':host(:not([disabled]):active)')).toContain('transform: scale(.97)');
  });

  it('transitions the press and the brightness, not the gradient', () => {
    const host = rule(':host');
    expect(host).toContain('transform var(--dur-instant) var(--ease-out)');
    expect(host).toContain('filter var(--dur-base) var(--ease-out)');
  });

  it('tints the press on touch with an inset, so it is not elevation', () => {
    const block = SOURCE.match(/@media \(hover: none\) \{([\s\S]*?)\n {4}\}/);
    expect(block).not.toBeNull();
    expect(block![1]).toContain(':host(:not([disabled]):active) { box-shadow: inset 0 0 0 100vmax var(--accent-soft); }');
  });

  it('casts no elevation shadow itself, and nothing glows on hover (v195 §1.2)', () => {
    const own = [...SOURCE.matchAll(/box-shadow:\s*([^;]+);/g)]
      .map(([, value]) => value.trim())
      .filter((value) => !value.startsWith('inset'));
    expect(own).toEqual([]);
    expect(MOTION).not.toContain('--glow-accent');
    expect(MOTION).not.toContain('button[sb-button].primary:not([disabled]):hover');
  });

  it('does not scale the press under Motion = Reduced', () => {
    expect(MOTION).toContain('[data-motion=reduced] button[sb-button]:not([disabled]):active { transform: none; }');
  });
});

/* v195 Phase 2, correction 6: the solid danger is the killswitch's alone.
 * Every other destructive control (close all, clear, restart, discard,
 * delete) is danger-quiet. The gallery is the primitive reference and shows
 * every variant, so it is the one other file allowed to name it. */
describe('v195: danger is the killswitch alone', () => {
  const SOLID_DANGER = /variant="danger"|'danger'(?!-)/;
  const ALLOWED = ['app/workspaces/gallery/gallery.ts', 'app/workspaces/risk/risk.ts'];

  it('appears as a button variant only on the Risk killswitch and in the gallery', () => {
    const users = allSources()
      .filter(({ name }) => name.startsWith('app/workspaces/') || name.startsWith('app/shell/'))
      .filter(({ source }) => SOLID_DANGER.test(stripComments(source)))
      .map(({ name }) => name);
    expect(users).toEqual(ALLOWED);
  });

  it('confirms the killswitch on the solid variant', () => {
    const risk = allSources().find(({ name }) => name === 'app/workspaces/risk/risk.ts')!.source;
    expect(risk).toContain('dangerVariant="danger"');
  });
});
