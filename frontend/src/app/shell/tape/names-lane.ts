import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink } from '@angular/router';

import { TapeStore } from '../../stores/tape.store';
import { Flash } from '../../ui/flash';
import { ABSENT, num, pct } from '../../ui/format';

/**
 * Lane B — flagged watchlist names with swingbot context.
 *
 * **The as-of badge lives in the end-cap, outside `.track`, and must stay
 * there.** A badge inside the moving element scrolls out of view, so the
 * freshness signal would blink in and out and be absent exactly when someone
 * glances at it. `names-lane.spec.ts` guards this.
 *
 * The track is rendered twice and translated -50%, which is what makes the
 * loop seamless rather than snapping back.
 *
 * Tick colour comes from `sbFlash`, which already flashes only on a real
 * change — never on first render, never on an identical re-render — so this
 * component adds no animation of its own for it.
 *
 * Price and change use `ui/format.ts`'s `num`/`pct` rather than Angular's
 * `DecimalPipe`/`DatePipe`, to match every other table/detail view in this
 * app and get the same never-drop-to-blank fallback for free. The as-of
 * clock is the one reading with no existing helper (`timeInZone` fixes a
 * zone; this wants the viewer's own), so it stays a local computed here.
 */
@Component({
  selector: 'sb-names-lane',
  standalone: true,
  imports: [RouterLink, Flash],
  changeDetection: ChangeDetectionStrategy.OnPush,
  styleUrl: './tape.css',
  template: `
    @if (tape.visible()) {
      <div class="lane" role="region" aria-label="Watchlist tape">
        <div class="cap">mine</div>
        <div class="viewport">
          <div class="track">
            @for (pass of [0, 1]; track pass) {
              @for (row of tape.rows(); track row.symbol) {
                <a class="tile" [routerLink]="['/watchlist', row.symbol]"
                   [sbFlash]="row.change_pct"
                   [attr.aria-hidden]="pass === 1 ? 'true' : null"
                   [attr.tabindex]="pass === 1 ? -1 : null">
                  <span class="sym">{{ row.symbol }}</span>
                  @if (row.price !== null) {
                    <span class="px">{{ num(row.price) }}</span>
                  }
                  @if (row.change_pct !== null) {
                    <span [class.up]="row.change_pct >= 0" [class.down]="row.change_pct < 0">
                      {{ pct(row.change_pct) }}
                    </span>
                  } @else {
                    <span class="ctx muted">no price</span>
                  }
                  @if (row.context_label) {
                    <span class="ctx" [class.muted]="row.context_kind === 'earnings'">
                      {{ row.context_label }}
                    </span>
                  }
                </a>
              }
            }
          </div>
        </div>
        <!-- Outside .track, deliberately. See the class comment. -->
        <div class="cap end as-of" [attr.title]="tape.asOf()"
             [attr.aria-label]="'Tape data as of ' + asOfTime()">
          <span aria-hidden="true">◷</span> {{ asOfTime() }}
        </div>
      </div>
    }
  `,
})
export class NamesLane {
  protected readonly tape = inject(TapeStore);
  protected readonly num = num;
  protected readonly pct = pct;

  protected readonly asOfTime = computed(() => {
    const iso = this.tape.asOf();
    if (!iso) return ABSENT;
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) return ABSENT;
    return parsed.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
  });
}
