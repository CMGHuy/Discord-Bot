import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { FocusTrap } from '../../ui/focus-trap';
import { LiveDock } from './live-dock';

/**
 * The Live dock as a sheet -- v203 (spec v202 §3, §4). Below 1024px the
 * dock never docks: the strip opens this instead, from the right on a
 * tablet and from the bottom on a phone. Focus is trapped (the More
 * sheet's pattern); Escape, the scrim and the dock's Close all close it.
 * `display: contents` on the host: the shell's grid gives it no cell.
 */
@Component({
  selector: 'sb-live-sheet',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FocusTrap, LiveDock],
  host: { '(document:keydown.escape)': 'onEscape()' },
  template: `
    @if (open()) {
      <div class="scrim" aria-hidden="true" (click)="closed.emit()"></div>
      <div class="sheet elev-overlay" [class.right]="side() === 'right'" [class.bottom]="side() === 'bottom'"
           [class.sb-sheet-in]="side() === 'bottom'" role="dialog" aria-modal="true" aria-label="Live" sbFocusTrap>
        <sb-live-dock variant="sheet" (close)="closed.emit()" />
      </div>
    }
  `,
  styles: `
    :host { display: contents; }
    .scrim { position: fixed; inset: 0; z-index: 30; background: var(--scrim-soft); }
    .sheet { position: fixed; z-index: 31; overflow-y: auto; overscroll-behavior: contain; background: var(--surface-overlay); }
    .right { inset: 0 0 0 auto; width: min(360px, calc(100vw - 48px)); border-left: 1px solid var(--border-strong); }
    .bottom {
      inset: auto 0 0 0; max-height: 85dvh; padding-bottom: env(safe-area-inset-bottom);
      border-top: 1px solid var(--border-strong); border-radius: var(--panel-radius) var(--panel-radius) 0 0;
    }
  `,
})
export class LiveSheet {
  readonly open = input(false);
  readonly side = input<'right' | 'bottom'>('right');
  readonly closed = output<void>();

  protected onEscape(): void {
    if (this.open()) this.closed.emit();
  }
}
