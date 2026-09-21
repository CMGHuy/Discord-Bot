import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

/** A failed fetch is not an empty chart (v94 H4); this replaces only panel body. */
@Component({
  selector: 'sb-panel-error', changeDetection: ChangeDetectionStrategy.OnPush, host: { role: 'alert' },
  template: `<div class="error"><span class="text">Could not load@if (message()) { <span class="why"> · {{ message() }}</span> }</span><button type="button" (click)="retry.emit()">Retry</button></div>`,
  styles: `:host { display:block; } .error { display:flex; align-items:center; justify-content:space-between; gap:var(--space-8); min-height:96px; padding:var(--space-14); border:1px dashed var(--neg); border-radius:var(--radius); background:var(--neg-soft); font-size:var(--text-table); color:var(--text); } .why { color:var(--text-secondary); } button { height:var(--control-h); padding:0 10px; border:1px solid var(--border-strong); border-radius:var(--radius); background:var(--surface-raised); color:var(--text); cursor:pointer; font:inherit; font-size:var(--text-chip); }`,
})
export class PanelError {
  readonly message = input<string | null>(null);
  readonly retry = output<void>();
}
