import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { Spinner } from './spinner';

const MOTION = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8');

describe('sb-spinner', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  function mount(label?: string) {
    const f = TestBed.createComponent(Spinner);
    if (label) f.componentRef.setInput('label', label);
    f.detectChanges();
    return f.nativeElement as HTMLElement;
  }

  it('is a status the screen reader can name, with a decorative ring', () => {
    const el = mount();
    expect(el.getAttribute('role')).toBe('status');
    expect(el.getAttribute('aria-label')).toBe('Loading');
    expect(el.querySelector('.ring')!.getAttribute('aria-hidden')).toBe('true');
  });

  it('says what is loading when told', () => {
    expect(mount('Updating win rate').getAttribute('aria-label')).toBe('Updating win rate');
  });

  it('slows under Motion = Off but never stops (a spinner is status)', () => {
    expect(MOTION).toMatch(/\[data-motion=off\] sb-spinner \.ring \{ animation-duration: 2\.4s !important; \}/);
    expect(MOTION).not.toMatch(/sb-spinner[^{]*\{[^}]*animation:\s*none/);
  });
});
