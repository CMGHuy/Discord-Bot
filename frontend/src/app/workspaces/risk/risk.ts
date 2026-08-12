import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Placeholder. The real workspace is NG49. */
@Component({
  selector: 'sb-risk',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1>Risk</h1><p class="todo">NG49</p>`,
  styles: `
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .todo { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class Risk {}
