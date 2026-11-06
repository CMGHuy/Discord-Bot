import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { NotificationHealth } from '../../api/models';
import { NotificationHealthPanel } from './notification-health-panel';

const EMPTY: NotificationHealth = {
  pending_count: 0, oldest_pending_age_seconds: null, blocked_count: 0,
};

function render(health: NotificationHealth | null, stale = false): HTMLElement {
  const fixture = TestBed.createComponent(NotificationHealthPanel);
  fixture.componentRef.setInput('health', health);
  fixture.componentRef.setInput('stale', stale);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('NotificationHealthPanel', () => {
  beforeEach(() => TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection()],
  }));

  it('shows a known empty queue without an alert', () => {
    const el = render(EMPTY);
    expect(el.textContent).toContain('No pending notifications');
    expect(el.querySelector('[role="alert"]')).toBeNull();
    expect(el.querySelector('[role="status"]')).not.toBeNull();
  });

  it('shows unknown for an absent health projection', () => {
    const el = render(null);
    expect(el.textContent).toContain('Notification delivery status unavailable');
    expect(el.textContent).not.toContain('No pending notifications');
    expect(el.querySelector('dl')).toBeNull();
  });

  it('does not display stale zeroes as healthy', () => {
    const el = render(EMPTY, true);
    expect(el.textContent).toContain('Notification delivery status unavailable');
    expect(el.textContent).not.toContain('No pending notifications');
    expect(el.querySelector('dl')).toBeNull();
  });

  it.each([
    [0, 900, false], [0, 901, true], [1, 0, true], [0, null, false],
  ] as const)('warns only for blocked work or age over fifteen minutes', (blocked, age, warning) => {
    const el = render({ pending_count: 2, blocked_count: blocked, oldest_pending_age_seconds: age });
    expect(el.querySelector('[role="alert"]') !== null).toBe(warning);
    expect(el.textContent?.includes('Delivery needs attention')).toBe(warning);
  });

  it('shows pending and blocked counts and the recorded oldest age', () => {
    const el = render({ pending_count: 3, blocked_count: 1, oldest_pending_age_seconds: 960 });
    const values = Array.from(el.querySelectorAll('dd')).map((entry) => entry.textContent?.trim());
    expect(values).toEqual(['3', '1', '16 min']);
    expect(el.textContent).toContain('same event ID');
    expect(el.textContent).toContain('retry');
  });

  it('keeps missing age unknown when work is pending', () => {
    const el = render({ ...EMPTY, pending_count: 1 });
    expect(el.textContent).toContain('Unknown');
    expect(el.textContent).not.toContain('No pending notifications');
  });
});
