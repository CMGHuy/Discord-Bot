import { ChangeDetectionStrategy, Component } from '@angular/core';

export const PNL_BASIS_LABEL = 'pre-tax, before modelled frictions';

@Component({
  selector: 'sb-pnl-basis',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: '<span class="pnl-basis">{{ label }}</span>',
  styles: `
    .pnl-basis {
      font-size: var(--text-micro);
      color: var(--text-faint);
      white-space: normal;
      overflow-wrap: anywhere;
    }
  `,
})
export class PnlBasis {
  protected readonly label = PNL_BASIS_LABEL;
}
