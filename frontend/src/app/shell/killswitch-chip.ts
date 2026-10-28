import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { RouterLink } from '@angular/router';

/**
 * The killswitch state, in the top bar on every device -- v195 Phase 3.
 *
 * The control lives in Risk's page header; this chip is the state, visible
 * from every page and two taps from the control on a phone (Risk is a tab).
 * "Armed" means trading runs; "Halted" means the killswitch is engaged and
 * the bot takes no new positions. The word carries the state, the loss
 * colour only repeats it, so it reads the same to a colour-blind eye.
 *
 * Renders nothing while the state is unknown (`null`): a chip that said
 * "Armed" before the first answer would be the one claim on the page that
 * must never be guessed.
 */
@Component({
  selector: 'sb-killswitch-chip',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink],
  template: `
    @if (on() !== null) {
      <a class="chip sb-hit" routerLink="/risk" [class.halted]="on()" [attr.aria-label]="label()">
        <span class="dot" aria-hidden="true"></span>{{ on() ? 'Halted' : 'Armed' }}
      </a>
    }
  `,
  styles: `
    :host { display: inline-flex; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-4);
      padding: 2px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      color: var(--text-secondary);
      font-size: var(--text-chip);
      line-height: 1.4;
      text-decoration: none;
      white-space: nowrap;
      transition: color var(--transition), border-color var(--transition);
    }
    .chip:hover { color: var(--text); border-color: var(--text-muted); }
    /* A status dot: the one full-round shape the radius rules allow (§1.5). */
    .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--pos); }
    .chip.halted {
      color: var(--neg);
      border-color: var(--neg);
      background: var(--neg-soft);
      font-weight: 600;
    }
    .chip.halted .dot { background: var(--neg); }
  `,
})
export class KillswitchChip {
  /** `null` until the shell's first `/risk/killswitch` answer. */
  readonly on = input<boolean | null>(null);

  protected readonly label = computed(() =>
    this.on() ? 'Killswitch on, trading halted. Open Risk' : 'Killswitch off, trading armed. Open Risk',
  );
}
