import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { Alarm } from './live/live-state';

/**
 * The top bar's alarm -- v203 (spec v202 §3 "Alarm chip", D5).
 *
 * The one live-state signal that must not depend on the dock being open:
 * it shows only while the bot is down, the event stream is dead or
 * degraded, or data is stale (the 900 s rule). The words are `alarmFor`'s
 * (live-state.ts), so the bar, the edge tab and the strip name a state the
 * same way. When nothing is wrong it renders nothing and the bar stays
 * clean. A tap opens the dock (DockState.reveal: the docked column from
 * 1024px, the sheet below).
 *
 * The warning tone, never the loss red: Phase 1 adds no colours, and red is
 * the engaged killswitch's. The host is a status region, so the alarm is
 * announced when it appears. Below 640px only the dot shows: the phone bar
 * has no room for the words, and the live strip directly under it names
 * the same state. The accessible name always carries the words.
 */
@Component({
  selector: 'sb-alarm-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'status' },
  template: `
    @if (alarm(); as current) {
      <button type="button" class="alarm-chip sb-hit" [attr.data-kind]="current.kind" [attr.aria-label]="label()"
              (click)="reveal.emit()">
        <span class="dot" aria-hidden="true"></span><span class="text">{{ current.text }}</span>
      </button>
    }
  `,
  styles: `
    :host { display: inline-flex; }
    .alarm-chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      padding: 2px var(--space-6);
      border: 1px solid var(--warn);
      border-radius: var(--chip-radius);
      background: var(--warn-soft);
      color: var(--warn);
      font: inherit;
      font-size: var(--text-chip);
      font-weight: 600;
      line-height: 1.4;
      white-space: nowrap;
      cursor: pointer;
    }
    /* A status dot: the one full-round shape the radius rules allow (§1.5). */
    .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--warn); }
    @media (max-width: 639px) { .text { display: none; } }
  `,
})
export class AlarmChip {
  /** `alarmFor(...)`: null while nothing is wrong. */
  readonly alarm = input<Alarm | null>(null);
  /** Asks the shell to open the Live dock. */
  readonly reveal = output<void>();

  protected readonly label = computed(() => {
    const current = this.alarm();
    return current ? `${current.text}. Open the live dock` : '';
  });
}
