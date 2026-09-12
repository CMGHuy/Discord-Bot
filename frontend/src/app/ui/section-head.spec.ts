import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { TestBed } from '@angular/core/testing';
import { Component, provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { SectionHead } from './section-head';

@Component({
  imports: [SectionHead],
  template: `
    <sb-section-head [heading]="'Trades'" [level]="level">
      <button actions type="button">Export</button>
    </sb-section-head>
  `,
})
class Host {
  level: 1 | 2 = 1;
}

@Component({
  imports: [SectionHead],
  template: `<sb-section-head heading="AAPL" [level]="1"><span status>as of 14:02</span><a back href="/trades">Trades</a></sb-section-head>`,
})
class SlotHost {}

@Component({
  imports: [SectionHead],
  template: `<sb-section-head><span actions>Unsaved settings</span></sb-section-head>`,
})
class BareHost {}

function render(level: 1 | 2 = 1) {
  const f = TestBed.createComponent(Host);
  f.componentInstance.level = level;
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('SectionHead', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('renders the heading at the requested level', () => {
    expect(render(1).querySelector('h1')!.textContent).toContain('Trades');
    expect(render(2).querySelector('h2')!.textContent).toContain('Trades');
  });

  it('projects actions beside the heading', () => {
    expect(render().querySelector('button')!.textContent).toContain('Export');
  });

  it('emits exactly one heading element', () => {
    expect(render().querySelectorAll('h1, h2').length).toBe(1);
  });

  it('renders no heading element at all when heading is omitted', () => {
    // R1-11: eight workspaces now project only actions/status, since the top
    // bar owns the title -- an empty <h1> would be worse than none.
    const f = TestBed.createComponent(BareHost);
    f.detectChanges();
    const el = f.nativeElement as HTMLElement;
    expect(el.querySelector('h1, h2')).toBeNull();
    expect(el.textContent).toContain('Unsaved settings');
  });
});

describe('SectionHead slots (v80 D4)', () => {
  const SOURCE = readFileSync(join(process.cwd(), 'src/app/ui/section-head.ts'), 'utf8');
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  function slots(): HTMLElement { const f = TestBed.createComponent(SlotHost); f.detectChanges(); return f.nativeElement as HTMLElement; }
  it('renders back before title', () => { const el = slots(); expect(el.querySelector('[back]')!.compareDocumentPosition(el.querySelector('h1')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy(); });
  it('keeps status in title group', () => { const el = slots(); const group = el.querySelector('h1')!.closest('.title-group'); expect(el.querySelector('[status]')!.closest('.title-group')).toBe(group); });
  it('keeps actions outside title group', () => expect(render().querySelector('button')!.closest('.title-group')).toBeNull());
  it('lets long title wrap', () => { expect(SOURCE).toMatch(/h1 \{[^}]*overflow-wrap: anywhere/); expect(SOURCE).toMatch(/h2 \{[^}]*overflow-wrap: anywhere/); });
});
