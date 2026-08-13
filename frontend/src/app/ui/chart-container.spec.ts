import { provideZonelessChangeDetection } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { beforeEach, describe, expect, it } from 'vitest';

import { ChartContainer } from './chart-container';

/* SR40 — spec Decision 10's first degraded state.
 *
 * "Endpoint fails → empty state naming the reason, with a retry — never a blank
 * pane." The other two states are pinned where they are decided rather than
 * here: `overlay: null` in `chart/strategy-overlay.spec.ts`, and a missing
 * indicator's pane in `chart/indicator-panes.spec.ts`.
 *
 * The retry is the part that needed building. This container has always shown
 * an error; it had no way to act on one, and "the chart will retry on the next
 * update" is not a retry — for a `not_found` there is no next update, and the
 * reader is left looking at a sentence with no way out of it.
 */

function render(inputs: Record<string, unknown>) {
  const fixture = TestBed.createComponent(ChartContainer);
  for (const [name, value] of Object.entries(inputs)) {
    fixture.componentRef.setInput(name, value);
  }
  fixture.detectChanges();
  return fixture;
}

describe('ChartContainer', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
  });

  it('names the reason it failed', () => {
    const element = render({ error: 'No chart data for trade t1.' }).nativeElement as HTMLElement;

    expect(element.textContent).toContain('No chart data for trade t1.');
  });

  it('offers a retry when the caller can act on one', () => {
    const fixture = render({ error: 'The admin is not responding.', canRetry: true });
    const button = (fixture.nativeElement as HTMLElement).querySelector('button');

    expect(button?.textContent).toContain('Retry');
  });

  it('emits the retry when it is pressed', () => {
    const fixture = render({ error: 'The admin is not responding.', canRetry: true });
    let retried = 0;
    fixture.componentInstance.retry.subscribe(() => retried++);

    (fixture.nativeElement as HTMLElement).querySelector('button')!.click();

    expect(retried).toBe(1);
  });

  it('offers no retry when the caller has nothing to retry with', () => {
    // The ticker-detail chart's store has no retry method. A button that does
    // nothing is worse than no button.
    const fixture = render({ error: 'The admin is not responding.' });

    expect((fixture.nativeElement as HTMLElement).querySelector('button')).toBeNull();
  });

  it('keeps the drawing surface mounted while it shows the failure', () => {
    // Never a blank pane, and never a REMOVED one: the chart library measures
    // this element, and an element that appears a tick later measures as zero
    // and renders as nothing.
    const element = render({ error: 'anything' }).nativeElement as HTMLElement;

    expect(element.querySelector('.surface')).not.toBeNull();
  });

  it('says an error beats a spinner when both are true', () => {
    // A refetch that failed should say so rather than spin forever.
    const element = render({ error: 'boom', loading: true }).nativeElement as HTMLElement;

    expect(element.textContent).toContain('boom');
    expect(element.querySelector('.spinner')).toBeNull();
  });
});
