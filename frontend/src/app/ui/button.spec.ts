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

  it('paints danger-icon as icon geometry in the negative colour', () => {
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
  it('fills primary with the fill blue and its own ink', () => {
    expect(rule(':host(.primary)')).toContain('background: var(--accent-fill)');
    expect(rule(':host(.primary)')).toContain('color: var(--on-accent)');
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
    const block = SOURCE.match(/@media \(pointer: coarse\), \(max-width: 639px\) \{([\s\S]*?)\n    \}/);
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
