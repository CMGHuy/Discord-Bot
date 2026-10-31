import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * A small turning ring: "this figure is being refetched".
 *
 * Sits inside the thing that is updating (a KPI card, a panel figure), never
 * replaces it -- the previous number stays on screen, dimmed by the host, so a
 * pan of the equity chart does not make the page jump. The same ring the data
 * table and chart container use (`sb-spin`), sized by `--spinner-size`.
 * Under Motion = Off it slows rather than stops (motion.css): a spinner is
 * status, not decoration.
 *
 * v195 Phase 2: the ring turns in the secondary grey, not the accent -- a
 * load is status, and the accent is kept for interactive state. The table's
 * and the chart frame's rings are the same rule (spinner.spec.ts).
 */
@Component({
  selector: 'sb-spinner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { role: 'status', '[attr.aria-label]': 'label()' },
  template: `<span class="ring" aria-hidden="true"></span>`,
  styles: `
    :host { display: inline-flex; line-height: 0; }
    .ring {
      width: var(--spinner-size, 14px);
      height: var(--spinner-size, 14px);
      box-sizing: border-box;
      border: 2px solid var(--border-strong);
      border-top-color: var(--text-secondary);
      border-radius: 50%;
      animation: sb-spin 700ms linear infinite;
    }
  `,
})
export class Spinner {
  /** What is loading, for assistive tech. */
  readonly label = input('Loading');
}
