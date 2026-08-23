import { ChangeDetectionStrategy, Component } from '@angular/core';

/**
 * A wrapping row of chips that DISPLAY rather than control.
 *
 * `tokens.spec.ts` exempts `chips` from the "no hand-rolled control row" gate
 * precisely because these are figures, not controls -- so this is not
 * `sb-control-row` and must not become it. A row of chips that are filters is
 * a control row and belongs in `sb-control-row` instead.
 */
@Component({
  selector: 'sb-chip-row',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<ng-content />`,
  styles: `
    :host {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: var(--space-6);
    }
  `,
})
export class ChipRow {}
