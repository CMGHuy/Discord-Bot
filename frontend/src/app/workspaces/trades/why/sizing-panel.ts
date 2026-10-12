import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Chip } from '../../../ui/chip';
import { num, share, text } from '../../../ui/format';
import { Panel } from '../../../ui/layout';

@Component({
  selector: 'sb-sizing-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Chip],
  template: `
    <sb-panel heading="Sizing">
      <p class="section-help">
        Position size is snapshotted when the trade opens. A trade with
        no sizing snapshot was logged before that feature existed.
      </p>
      <dl>
        <div><dt>Shares</dt><dd class="sb-num">{{ fmtNum(shares(), 0) }}</dd></div>
        <div><dt>Deployed</dt><dd class="sb-num">{{ fmtNum(positionValue()) }}</dd></div>
        <div><dt>Sizing mode</dt><dd>{{ fmtText(sizingMode()) }}</dd></div>
        <div><dt>Working stop</dt><dd class="sb-num">{{ fmtNum(workingStop()) }}</dd></div>
        <div>
          <dt>Gap risk (p90)</dt>
          <dd class="gap-risk sb-num">
            <span>{{ fmtShare(gapP90Pct(), 2) }}</span>
            @if (gapFragile() === true) {
              <sb-chip label="fragile" tone="warn" [caps]="false"
                title="The stop sits inside 90th-percentile gap noise: an overnight gap can jump it." />
            }
          </dd>
        </div>
      </dl>
    </sb-panel>
  `,
  styles: `
    :host { display: block; min-width: 0; }
    dl { display: grid; gap: var(--space-6); margin: 0; }
    dl > div { display: flex; justify-content: space-between; gap: var(--space-10); }
    dt { color: var(--text-secondary); }
    dt, dd { font-size: var(--text-table); }
    dd { margin: 0; color: var(--text); }
    .gap-risk { display: flex; align-items: center; flex-wrap: wrap; justify-content: flex-end; gap: var(--space-6); }
  `,
})
export class SizingPanel {
  readonly shares = input<number | null>(null);
  readonly positionValue = input<number | null>(null);
  readonly sizingMode = input<string | null>(null);
  readonly workingStop = input<number | null>(null);
  readonly gapP90Pct = input<number | null>(null);
  readonly gapFragile = input<boolean | null>(null);

  protected readonly fmtNum = num;
  protected readonly fmtShare = share;
  protected readonly fmtText = text;
}
