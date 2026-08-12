import { ChangeDetectionStrategy, Component } from '@angular/core';

/** Placeholder. The real workspace is NG42. */
@Component({
  selector: 'sb-trades',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1>Trades</h1><p class="todo">NG42</p>`,
  styles: `
    h1 { margin: 0; font-size: var(--text-title); font-weight: 600; }
    .todo { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class Trades {}
