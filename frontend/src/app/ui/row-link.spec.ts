import { TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it } from 'vitest';

import { RowLink } from './row-link';

function render(link: unknown[]) {
  const f = TestBed.createComponent(RowLink);
  f.componentRef.setInput('link', link);
  f.detectChanges();
  return f.nativeElement as HTMLElement;
}

describe('RowLink', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideZonelessChangeDetection(), provideRouter([])],
    });
  });

  it('renders a real anchor so the row can be opened in a new tab', () => {
    const a = render(['/trades', 7]).querySelector('a')!;
    expect(a.tagName).toBe('A');
    expect(a.getAttribute('href')).toBe('/trades/7');
  });

  it('covers the whole row so the click target is the row, not the text', () => {
    expect(render(['/trades', 7]).querySelector('a')!.className).toContain('row-link');
  });
});
