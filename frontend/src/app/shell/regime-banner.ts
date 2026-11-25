import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { RegimeStore } from '../stores/regime.store';
import { Chip } from '../ui/chip';

/** v239: the daily trend (bear regime, shadow) as a strip under the tape.
 *  Collapsed it reads "Trend: <label>", the confirmed-session count, the
 *  pullback chip and the number line (hidden inline on a phone); expanded it
 *  adds the plain-words sentence. Renders nothing on NORMAL, off or loading. */
@Component({
  selector: 'sb-regime-banner',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Chip],
  template: `
    @if (banner(); as b) {
      @if (b.kind === 'none') {
        <div class="regime-strip" data-tone="muted" role="status">Regime: no reading</div>
      } @else {
        <div class="regime-strip" [attr.data-tone]="b.tone">
          <button type="button" class="regime-toggle" aria-controls="regime-detail"
                  [attr.aria-expanded]="open()" [attr.aria-label]="b.accessibleName" (click)="open.set(!open())">
            <span class="lead">Trend: {{ b.label }}</span>
            @if (b.since !== null) {
              <span class="since">since {{ b.since }} {{ b.since === 1 ? 'session' : 'sessions' }}</span>
            }
            @if (b.pullback) { <sb-chip label="Pullback watch" tone="info" [caps]="false" /> }
            @if (b.numbers) { <span class="numbers num">{{ b.numbers }}</span> }
          </button>
          <div id="regime-detail" class="regime-detail" [hidden]="!open()">
            @if (b.numbers) { <p class="num">{{ b.numbers }}</p> }
            @if (b.words) { <p>{{ b.words }}</p> }
          </div>
        </div>
      }
    }
  `,
  styles: `
    :host { display: block; }
    .regime-strip { border-bottom: 1px solid var(--warn); background: var(--warn-soft); color: var(--warn); }
    .regime-strip[data-tone='bear'] { border-color: var(--neg); background: var(--neg-soft); color: var(--neg); }
    .regime-strip[data-tone='muted'] { display: flex; align-items: center; min-height: 44px;
      padding: 0 var(--space-14); border-color: var(--border); background: transparent;
      color: var(--text-muted); font-size: var(--text-chip); }
    .regime-toggle { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-6) var(--space-10);
      width: 100%; min-height: 44px; padding: var(--space-6) var(--space-14); border: 0; background: none;
      color: inherit; font: inherit; font-size: var(--text-chip); text-align: left; cursor: pointer; }
    .lead { font-weight: 650; }
    .since, .numbers { color: var(--text-secondary); }
    .regime-detail { padding: 0 var(--space-14) var(--space-8); font-size: var(--text-chip); color: var(--text-secondary); }
    .regime-detail p { margin: 0; }
    @media (max-width: 639px) { .numbers { display: none; } }
  `,
})
export class RegimeBannerComponent {
  protected readonly banner = inject(RegimeStore).banner;
  protected readonly open = signal(false);
}
