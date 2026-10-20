import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { Button, type ButtonVariant } from './button';

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

  for (const variant of ['primary', 'secondary', 'danger', 'ghost', 'icon',
                         'chip', 'segment', 'link'] as ButtonVariant[]) {
    it(`puts the ${variant} class on the native button`, () => {
      expect(render(variant).classList.contains(variant)).toBe(true);
    });
  }

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
  /* v167 §3: the fill is the tier-3 gradient. A gradient is an image, so it
   * must be `background`, never `background-color` (which would drop it). */
  it('fills primary with the button gradient and its own ink', () => {
    const primary = rule(':host(.primary)');
    expect(primary).toContain('background: var(--btn-fill)');
    expect(primary).toContain('color: var(--on-accent)');
    expect(primary).not.toContain('background-color');
  });

  it('hovers primary onto the lighter gradient, not a flat color-mix', () => {
    const hover = rule(':host(.primary:not([disabled]):hover)');
    expect(hover).toContain('background: var(--btn-fill-hover)');
    expect(hover).not.toContain('color-mix');
  });

  it('draws secondary as a hairline, not a raised fill', () => {
    const r = rule(':host(.secondary)');
    expect(r).toContain('background: transparent');
    expect(r).toContain('border-color: var(--border-strong)');
  });

  it('outlines danger in the loss colour and fills it on hover', () => {
    expect(rule(':host(.danger)')).toContain('border-color: var(--neg)');
    expect(rule(':host(.danger:not([disabled]):hover)')).toContain('background: var(--neg)');
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
 * hover brightens it with a filter and motion.css adds the accent glow; every
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

  it('casts no elevation shadow itself: the glow lives in motion.css', () => {
    const own = [...SOURCE.matchAll(/box-shadow:\s*([^;]+);/g)]
      .map(([, value]) => value.trim())
      .filter((value) => !value.startsWith('inset'));
    expect(own).toEqual([]);
    expect(MOTION).toContain(
      '@media (hover: hover) { button[sb-button].primary:not([disabled]):hover { box-shadow: var(--glow-accent); } }',
    );
  });

  it('does not scale the press under Motion = Reduced', () => {
    expect(MOTION).toContain('[data-motion=reduced] button[sb-button]:not([disabled]):active { transform: none; }');
  });
});
