import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * The viewer's read-only label in the top bar (v207). Presentation only: a
 * non-interactive label, not a link or a control, so it takes no focus stop
 * and needs no 44px target.
 *
 * On a phone `compact` shortens the visible text to "Read-only" so a
 * 64-character username cannot push the bar into overflow; elsewhere the name
 * is truncated with an ellipsis past 16rem. The full sentence stays in `title`
 * and in a visually hidden span at every width.
 */
@Component({
  selector: 'sb-read-only-badge',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="badge" [attr.title]="spoken()"><span aria-hidden="true">{{ visible() }}</span><span class="sr-only">{{ spoken() }}</span></span>`,
  styles: `
    :host { display: inline-flex; min-width: 0; }
    .badge {
      display: inline-block;
      max-width: 16rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      padding: 2px var(--space-6);
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }
    .sr-only {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0 0 0 0);
      white-space: nowrap;
    }
  `,
})
export class ReadOnlyBadge {
  readonly username = input.required<string>();
  readonly compact = input(false);

  protected readonly visible = computed(() => (this.compact() ? 'Read-only' : `Read-only · ${this.username()}`));
  protected readonly spoken = computed(() => `Read-only account, signed in as ${this.username()}`);
}
