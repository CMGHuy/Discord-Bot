import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

import { LiveWarning, warningLabel } from './live-state';

/** The collapsed dock's and the strip's accessible label: every warning named. */
export function liveSummaryLabel(warnings: readonly LiveWarning[], heatText: string, awaitingCount: number | null): string {
  const parts = ['Open the live dock'];
  if (warnings.length > 0) parts.push(`Warning: ${warnings.map(warningLabel).join(', ')}`);
  parts.push(heatText);
  if (awaitingCount !== null) parts.push(`${awaitingCount} awaiting order`);
  return parts.join('. ');
}

/**
 * The collapsed Live dock -- v203 (spec v202 §4, D4). A 40px edge tab: a
 * status dot, "Live" rotated, the heat figure and the awaiting count. Any
 * warning tones it and is named in its label, so a collapsed choice can
 * never hide an alarm; it never forces the dock open.
 */
@Component({
  selector: 'sb-live-edge-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" class="edge-tab sb-hit" [class.warn]="warn()" [attr.aria-label]="label()" (click)="expand.emit()">
      <span class="dot" aria-hidden="true"></span>
      <span class="word" aria-hidden="true">Live</span>
      <span class="heat" aria-hidden="true">{{ heatText() }}</span>
      @if (awaitingCount() !== null) { <span class="count" aria-hidden="true">{{ awaitingCount() }}</span> }
    </button>
  `,
  styles: `
    :host { display: block; height: 100%; }
    .edge-tab {
      display: flex; flex-direction: column; align-items: center; gap: var(--space-10);
      width: 40px; height: 100%; padding: var(--space-10) 0;
      border: 0; background: transparent; color: var(--text-secondary);
      font: inherit; font-size: var(--text-micro); cursor: pointer;
      transition: background var(--transition), color var(--transition);
    }
    .edge-tab:hover { background: var(--surface-raised); color: var(--text); }
    .edge-tab:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--pos); }
    .word, .heat { writing-mode: vertical-rl; transform: rotate(180deg); white-space: nowrap; }
    .word { color: var(--text); font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase; }
    .heat { font-variant-numeric: tabular-nums; }
    .count { min-width: 20px; padding: 2px 4px; border-radius: var(--radius-sm); background: var(--surface-raised); color: var(--text); text-align: center; font-variant-numeric: tabular-nums; }
    .warn { background: var(--warn-soft); color: var(--warn); }
    .warn .dot { background: var(--warn); }
    .warn .word { color: var(--warn); }
  `,
})
export class LiveEdgeTab {
  readonly warnings = input<readonly LiveWarning[]>([]);
  readonly heatText = input.required<string>();
  readonly awaitingCount = input<number | null>(null);
  readonly expand = output<void>();

  protected readonly warn = computed(() => this.warnings().length > 0);
  protected readonly label = computed(() => liveSummaryLabel(this.warnings(), this.heatText(), this.awaitingCount()));
}
