import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { StatusIndicator } from '../../ui/status-indicator';
import { COST_CAPTION, OutcomeTile, PAPER_FILLS_LINE, STALE_FLAG } from './outcome-tiles';

@Component({
  selector: 'sb-outcome-strip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [StatusIndicator],
  template: `
    <div class="strip">
      @for (tile of tiles(); track tile.id) {
        <div class="tile" [attr.data-tile]="tile.id">
          <div class="sb-label">{{ tile.label }}</div>
          <div class="tile-value num" [class.pos]="tile.tone === 'pos'" [class.neg]="tile.tone === 'neg'">
            @if (tile.indicator; as indicator) {
              <sb-status-indicator [status]="indicator.status" [current]="indicator.current"
                [entry]="indicator.entry" [stop]="indicator.stop" [target]="indicator.target" />
            } @else {
              {{ tile.value }}
            }
            @if (tile.stale) { <span class="stale-flag">{{ staleFlag }}</span> }
          </div>
          @if (tile.sub) { <div class="tile-sub">{{ tile.sub }}</div> }
          @if (tile.costCaption) { <div class="tile-caption">{{ costCaption }}</div> }
        </div>
      }
    </div>
    <p class="strip-foot">{{ paperFillsLine }}</p>
  `,
  styles: `
    :host { display: block; }
    .strip { display: flex; flex-wrap: wrap; gap: var(--space-14); }
    .tile {
      flex: 1 1 120px; min-width: 0; display: flex; flex-direction: column;
      gap: var(--space-6); padding: var(--space-14);
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--panel-radius);
    }
    .tile-value { font-size: var(--text-title); overflow-wrap: anywhere; }
    .tile-sub { color: var(--text-secondary); font-size: var(--text-table); }
    .tile-caption, .strip-foot, .stale-flag { color: var(--text-muted); font-size: var(--text-micro); }
    .strip-foot { margin: var(--space-8) 0 0; }
    .stale-flag { margin-inline-start: var(--space-6); }
  `,
})
export class OutcomeStrip {
  readonly tiles = input.required<readonly OutcomeTile[]>();
  protected readonly costCaption = COST_CAPTION;
  protected readonly paperFillsLine = PAPER_FILLS_LINE;
  protected readonly staleFlag = STALE_FLAG;
}
