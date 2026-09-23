import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { Matrix } from './matrix';

const LABELS = ['AAPL', 'MSFT', 'XOM'];
const VALUES = [
  [1, 0.68, 0.12],
  [0.68, 1, null],
  [0.12, null, 1],
];

function render(inputs: Record<string, unknown> = {}): HTMLElement {
  const f = TestBed.createComponent(Matrix);
  f.componentRef.setInput('labels', LABELS);
  f.componentRef.setInput('values', VALUES);
  for (const [key, val] of Object.entries(inputs)) f.componentRef.setInput(key, val);
  f.detectChanges();
  return (f.nativeElement as HTMLElement).querySelector('.matrix')!;
}

describe('Matrix (v85 D38)', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders one row per label', () => {
    expect(render().querySelectorAll('tbody tr').length).toBe(3);
  });

  it('renders a correlation to two decimals', () => {
    expect(render().querySelector('tbody tr td')!.textContent).toContain('1.00');
  });

  it('renders a missing pair as no-value, never as zero correlation', () => {
    const cells = render().querySelectorAll('tbody tr')[1].querySelectorAll('td');
    expect(cells[2].textContent!.trim()).toBe('—');
    expect(cells[2].classList).toContain('missing');
  });

  it('bands a cell by magnitude so the heat is readable', () => {
    const cells = render().querySelectorAll('tbody tr')[0].querySelectorAll('td');
    expect(cells[0].classList).toContain('b5');
    expect(cells[2].classList).toContain('b1');
  });

  it('marks cells that fall inside one of the bot clusters', () => {
    const el = render({ clusters: [['AAPL', 'MSFT']] });
    const cells = el.querySelectorAll('tbody tr')[0].querySelectorAll('td');
    expect(cells[1].classList).toContain('clustered');
    expect(cells[2].classList).not.toContain('clustered');
  });

  it('states cluster membership in text, not by outline alone', () => {
    const el = render({ clusters: [['AAPL', 'MSFT']] });
    const cells = el.querySelectorAll('tbody tr')[0].querySelectorAll('td');
    expect(cells[1].getAttribute('title')).toContain('same cluster');
  });

  it('scrolls inside its own container rather than the page', () => {
    expect(render().classList).toContain('scroll-x');
  });
});

/* -- v95 D2 -- sticky row headers -------------------------------------------- */

describe('sb-matrix row headers', () => {
  const src = readFileSync(join(process.cwd(), 'src/app/ui/matrix.ts'), 'utf8');

  it('pins the row header against horizontal scroll', () => {
    // Without this, scrolling right to reach a correlation scrolls away the
    // label naming the pair. A number you cannot attribute is not data.
    expect(src).toMatch(/th\[scope=["']row["']\][^{]*\{[^}]*position:\s*sticky/s);
    expect(src).toMatch(/th\[scope=["']row["']\][^{]*\{[^}]*left:\s*0/s);
  });
});
