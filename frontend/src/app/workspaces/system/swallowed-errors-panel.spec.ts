import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { SystemHealth } from '../../api/models';
import { SwallowedErrorsPanel, swallowedLines } from './swallowed-errors-panel';

const NOW = Date.parse('2026-10-10T12:00:00Z');

const HEALTH: SystemHealth = {
  providers: [],
  thresholds: { fallback_pct: 20, empty_pct: 5 },
  swallowed: [
    { process: 'admin', tag: 'runstate.read_heartbeat', count: 1,
      first_at: '2026-10-10T11:00:00Z', last_at: '2026-10-10T11:00:00Z',
      last_error: 'OperationalError: connection refused' },
    { process: 'bot', tag: 'scan.run_bounded', count: 7,
      first_at: '2026-10-10T06:05:00Z', last_at: '2026-10-10T09:00:00Z',
      last_error: 'TimeoutError: cold-fetch chunk 3' },
    { process: 'bot', tag: 'marketdata.price_batch', count: 7,
      first_at: null, last_at: null, last_error: null },
  ],
  bot_counts_since: '2026-10-10T06:00:00Z',
};

function render(health: SystemHealth | null): HTMLElement {
  const fixture = TestBed.createComponent(SwallowedErrorsPanel);
  fixture.componentRef.setInput('health', health);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('swallowed error rows', () => {
  it('sorts by count, then process, then tag', () => {
    expect(swallowedLines(HEALTH, NOW).map((l) => l.tag)).toEqual([
      'marketdata.price_batch',
      'scan.run_bounded',
      'runstate.read_heartbeat',
    ]);
  });

  it('shows last seen as a relative age', () => {
    const lines = swallowedLines(HEALTH, NOW);

    expect(lines.find((l) => l.tag === 'scan.run_bounded')!.lastSeen).toBe('3h ago');
    expect(lines.find((l) => l.tag === 'runstate.read_heartbeat')!.lastSeen).toBe('1h ago');
  });

  it('renders an unknown time or error as an em dash', () => {
    const line = swallowedLines(HEALTH, NOW).find((l) => l.tag === 'marketdata.price_batch')!;

    expect(line.lastSeen).toBe('—');
    expect(line.lastError).toBe('—');
  });

  it('has no lines before the first answer', () => {
    expect(swallowedLines(null)).toEqual([]);
  });
});

describe('SwallowedErrorsPanel', () => {
  beforeEach(() => TestBed.configureTestingModule({
    providers: [provideZonelessChangeDetection()],
  }));

  it('renders one row per process and tag, with the process named', () => {
    const rows = render(HEALTH).querySelectorAll('tbody tr');

    expect(rows).toHaveLength(3);
    expect(rows[2].textContent).toContain('admin');
    expect(rows[0].textContent).toContain('bot');
  });

  it('says when the bot counts began', () => {
    expect(render(HEALTH).textContent).toContain('Bot counts since');
  });

  it('says so when the bot has not reported counts yet', () => {
    const el = render({ ...HEALTH, bot_counts_since: null });

    expect(el.textContent).toContain('has not reported its counts yet');
  });

  it('says so when nothing was swallowed', () => {
    const el = render({ ...HEALTH, swallowed: [] });

    expect(el.querySelector('table')).toBeNull();
    expect(el.textContent).toContain('None since the processes started');
  });
});
