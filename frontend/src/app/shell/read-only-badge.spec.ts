import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ReadOnlyBadge } from './read-only-badge';

describe('ReadOnlyBadge (v207)', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));

  function render(username: string, compact = false): HTMLElement {
    const fixture = TestBed.createComponent(ReadOnlyBadge);
    fixture.componentRef.setInput('username', username);
    fixture.componentRef.setInput('compact', compact);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  const visible = (el: HTMLElement) => el.querySelector('[aria-hidden="true"]')!.textContent!.trim();
  const spoken = (el: HTMLElement) => el.querySelector('.sr-only')!.textContent!.trim();

  it('reads "Read-only · <name>" on a tablet or desktop', () => {
    const el = render('viewer1');
    expect(visible(el)).toBe('Read-only · viewer1');
    expect(spoken(el)).toBe('Read-only account, signed in as viewer1');
    expect(el.querySelector('.badge')!.getAttribute('title')).toBe('Read-only account, signed in as viewer1');
  });

  it('drops the name from the visible text on a phone, never from the spoken one', () => {
    const name = 'a'.repeat(64);
    const el = render(name, true);
    expect(visible(el)).toBe('Read-only');
    expect(spoken(el)).toBe(`Read-only account, signed in as ${name}`);
  });

  it('is a label, not a control: no link, no button, no tab stop', () => {
    const el = render('viewer1');
    expect(el.querySelector('a, button, [tabindex]')).toBeNull();
  });

  it('truncates a long name rather than growing the bar', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/read-only-badge.ts'), 'utf8');
    expect(source).toMatch(/max-width:\s*16rem/);
    expect(source).toMatch(/text-overflow:\s*ellipsis/);
    expect(source).toMatch(/white-space:\s*nowrap/);
  });
});
