import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Placeholder. The real workspace is NG51. */
@Component({
  selector: 'sb-universe',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1>Universe</h1><p class="todo">NG51</p>`,
  styles: `
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .todo { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class Universe {}
