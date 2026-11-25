import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { Hint } from '../../ui/hint';

/**
 * A scale-out leg's name ("Leg 2 of 2 · Runner at T2") with its explanation as
 * a tooltip on the text itself -- no separate info icon beside it. The text
 * takes focus (tabindex 0) so a keyboard or a tap opens the tooltip the way a
 * mouse hover does; `sb-hint` in anchor mode does the rest.
 */
@Component({
  selector: 'sb-leg-name',
  imports: [Hint],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span #name class="name" tabindex="0">{{ label() }}</span>
    <sb-hint [anchor]="name" [wide]="true" [text]="help()" [label]="'About ' + label()" />`,
  styles: `
    :host { display: inline-flex; align-items: center; }
    .name { cursor: help; text-decoration: underline dotted; text-underline-offset: 3px; }
    .name:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    /* The identifier above the label is another target. Give the leg its own
       space on touch layouts so the two controls do not share a hit area. */
    @media (pointer: coarse), (max-width: 1023px) {
      .name {
        display: inline-flex;
        align-items: flex-end;
        min-width: var(--hit-min);
        min-height: var(--control-h);
        padding-block-end: var(--space-4);
      }
    }
  `,
})
export class LegName {
  readonly label = input.required<string>();
  readonly help = input.required<string>();
}
