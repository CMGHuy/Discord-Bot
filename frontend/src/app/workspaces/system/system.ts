import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Placeholder. The real workspace is NG50. */
@Component({
  selector: 'sb-system',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1>System</h1><p class="todo">NG50</p>`,
  styles: `
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .todo { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class System {}
