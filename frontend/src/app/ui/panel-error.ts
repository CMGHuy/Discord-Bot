import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/** A failed fetch is not an empty chart (v94 H4); this replaces only panel body.
 *
 * v195 Phase 2: the one error style, shared declaration for declaration with
 * sb-async's error branch (async.spec.ts): a 2px --neg stripe on the neg
 * tint, the message in body text, Retry as a quiet bordered control. No
 * dashed box -- the panel around it is the frame. */
@Component({
  selector: 'sb-panel-error', changeDetection: ChangeDetectionStrategy.OnPush, host: { role: 'alert' },
  template: `<div class="error"><span class="text">Could not load@if (message()) { <span class="why"> · {{ message() }}</span> }</span><button type="button" class="retry" (click)="retry.emit()">Retry</button></div>`,
  styles: `
    :host { display: block; }
    .error {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-8);
      min-height: 96px;
      padding: var(--space-14) var(--panel-pad);
      border-left: 2px solid var(--neg);
      border-radius: var(--radius-sm);
      background: var(--neg-soft);
      color: var(--text);
      font-size: var(--text-table);
    }
    .why { color: var(--text-secondary); }
    .retry {
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border: 1px solid var(--border-strong);
      border-radius: var(--control-radius);
      background: transparent;
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: background var(--transition);
    }
    .retry:hover { background: var(--surface-raised); }
    .retry:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
  `,
})
export class PanelError {
  readonly message = input<string | null>(null);
  readonly retry = output<void>();
}
