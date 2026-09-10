import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import type { AsyncEmptyReason } from './async';
import { EmptyStateComponent } from './empty-state';

const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/empty-state.ts'), 'utf8');
function render(title: string, hint?: string, reason?: AsyncEmptyReason): HTMLElement {
  const f = TestBed.createComponent(EmptyStateComponent); f.componentRef.setInput('title', title);
  if (hint !== undefined) f.componentRef.setInput('hint', hint); if (reason !== undefined) f.componentRef.setInput('reason', reason);
  f.detectChanges(); return f.nativeElement as HTMLElement;
}
describe('EmptyStateComponent (v80 D4)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  it('states title and hint', () => { const el = render('No trades match this filter', 'Clear the filters.'); expect(el.querySelector('.empty-title')!.textContent!.trim()).toBe('No trades match this filter'); expect(el.querySelector('.empty-hint')!.textContent!.trim()).toBe('Clear the filters.'); });
  it('omits hint when absent', () => expect(render('No trades yet').querySelector('.empty-hint')).toBeNull());
  it('names a measured zero', () => { const reason = render('No trades', undefined, 'measured-zero').querySelector('.reason')!; expect(reason.textContent!.trim()).toBe('Result: 0'); expect(reason.classList).toContain('sb-label'); });
  it('names data not arrived', () => expect(render('No trades', undefined, 'no-data-yet').querySelector('.reason')!.textContent!.trim()).toBe('Awaiting data'));
  it('shows no reason until specified', () => expect(render('No trades').querySelector('.reason')).toBeNull());
  it('draws dashed hairline box', () => expect(SOURCE).toMatch(/\.empty \{[^}]*border: 1px dashed var\(--border-strong\)/));
});
