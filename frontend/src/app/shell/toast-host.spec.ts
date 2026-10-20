import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ToastHost } from './toast-host';
import { ToastService } from './toast.service';

describe('ToastHost', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  afterEach(() => vi.useRealTimers());

  function mount() {
    const fixture = TestBed.createComponent(ToastHost);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const shown = () => [...el.querySelectorAll<HTMLButtonElement>('.toast')];
    return { fixture, shown, toasts: TestBed.inject(ToastService) };
  }

  it('renders each toast as an overlay button carrying its kind', () => {
    const { fixture, shown, toasts } = mount();
    toasts.show('Scan triggered');
    toasts.show('Could not close trade', 'error');
    fixture.detectChanges();
    expect(shown().map((button) => button.textContent!.trim())).toEqual(['Scan triggered', 'Could not close trade']);
    expect(shown()[0].classList).toContain('toast');
    expect(shown()[0].classList).toContain('elev-overlay');
    expect(shown()[0].classList).toContain('info');
    expect(shown()[1].classList).toContain('error');
  });

  it('removes a clicked toast; in jsdom the leave animation is skipped, so at once', async () => {
    const { fixture, shown, toasts } = mount();
    toasts.show('Scan triggered');
    fixture.detectChanges();
    shown()[0].click();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(shown()).toEqual([]);
  });

  it('auto-dismisses an info toast after its time, and keeps an error', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const { fixture, shown, toasts } = mount();
    toasts.show('Saved', 'info', 4000);
    toasts.show('Could not close trade', 'error');
    vi.advanceTimersByTime(4000);
    vi.useRealTimers();
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(shown().map((button) => button.textContent!.trim())).toEqual(['Could not close trade']);
  });

  /* v168 §3a: the item pops in and fades out. Source text, because TestBed
   * disables animations and jsdom has no getAnimations(), so neither class
   * is ever observable on a rendered node here. */
  it('enters with sb-pop-in and leaves with sb-fade-out, both defined in motion.css', () => {
    const source = readFileSync(join(process.cwd(), 'src/app/shell/toast-host.ts'), 'utf8');
    const button = source.match(/<button class="toast elev-overlay"[^>]*>/)![0];
    expect(button).toContain('animate.enter="sb-pop-in"');
    expect(button).toContain('animate.leave="sb-fade-out"');
    const motion = readFileSync(join(process.cwd(), 'src/styles/motion.css'), 'utf8');
    expect(motion).toMatch(/^\.sb-pop-in \{/m);
    expect(motion).toMatch(/^\.sb-fade-out \{/m);
  });
});
