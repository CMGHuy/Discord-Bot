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
});
