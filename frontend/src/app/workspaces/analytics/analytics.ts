import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Placeholder. The real workspace is NG48. */
@Component({
  selector: 'sb-analytics',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1>Analytics</h1><p class="todo">NG48</p>`,
  styles: `
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .todo { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class Analytics {}
