import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/** v201: a total that leaves positions out says so, instead of looking whole. */
@Component({
  selector: 'sb-incomplete-note',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `@if (missing() > 0) {<span class="incomplete" role="note">incomplete: {{ missing() }} {{ noun() }} unpriced</span>}`,
  styles: `
    :host { display: inline; }
    .incomplete { color: var(--warn); font-size: var(--text-micro); }
  `,
})
export class IncompleteNote {
  readonly missing = input.required<number>();
  protected readonly noun = computed(() => (this.missing() === 1 ? 'position' : 'positions'));
}
