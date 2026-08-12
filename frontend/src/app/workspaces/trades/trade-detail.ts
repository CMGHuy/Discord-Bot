import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/** Placeholder. The real detail view is NG43.
 *
 * `id` arrives as an input() rather than through ActivatedRoute, via
 * withComponentInputBinding() -- which makes the parameter a normal signal
 * input and keeps the component testable without a router.
 */
@Component({
  selector: 'sb-trade-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<h1>{{ id() }}</h1><p class="todo">NG43</p>`,
  styles: `
    h1 { margin: 0; font-family: var(--font-mono); font-size: var(--text-title); }
    .todo { color: var(--text-faint); font-size: var(--text-table); }
  `,
})
export class TradeDetail {
  readonly id = input.required<string>();
}
