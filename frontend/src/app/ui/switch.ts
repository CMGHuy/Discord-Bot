import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

let nextId = 0;

/**
 * An on/off switch (spec v227 §4): a native button with `role="switch"`, so
 * Space and Enter toggle it and the visible label is its accessible name.
 *
 * `mixed` is for a group switch over a partly-on set (a Settings family): it
 * reads `aria-checked="mixed"`, and a tap turns the whole set on. Controlled:
 * it emits the wanted value and shows whatever `checked` the parent passes back.
 *
 * At least --hit-min tall, which tokens.css raises to 44px on touch and below
 * 1024px; the label wraps rather than truncating.
 */
@Component({
  selector: 'sb-switch',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <button type="button" role="switch" class="switch" [attr.aria-checked]="ariaChecked()"
            [disabled]="disabled()" [attr.aria-describedby]="hint() ? hintId : null" (click)="toggle()">
      <span class="track" [class.on]="checked() && !mixed()" [class.mixed]="mixed()" aria-hidden="true">
        <span class="thumb"></span>
      </span>
      <span class="label">{{ label() }}</span>
    </button>
    @if (hint(); as text) {
      <span class="hint" [id]="hintId">{{ text }}</span>
    }
  `,
  styles: `
    :host { display: flex; flex-direction: column; min-width: 0; }
    .switch {
      display: inline-flex;
      align-items: center;
      gap: var(--space-8);
      min-height: var(--hit-min);
      padding: 0;
      border: 0;
      background: transparent;
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
      cursor: pointer;
    }
    .switch:disabled { opacity: 0.45; cursor: default; }
    .switch:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .label { min-width: 0; overflow-wrap: anywhere; }
    .track {
      position: relative;
      flex: none;
      width: 28px;
      height: 16px;
      border: 1px solid var(--border-strong);
      border-radius: var(--chip-radius);
      background: var(--surface-raised);
      transition: background var(--transition), border-color var(--transition);
    }
    .thumb {
      position: absolute;
      top: 2px;
      left: 2px;
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: var(--text-muted);
      transition: transform var(--transition);
    }
    .track.on { background: var(--accent-soft); border-color: var(--accent); }
    .track.on .thumb { transform: translateX(12px); background: var(--accent); }
    .track.mixed .thumb { transform: translateX(6px); background: var(--accent); }
    .hint { padding-left: calc(28px + var(--space-8)); color: var(--text-muted); font-size: var(--text-chip); }
  `,
})
export class Switch {
  readonly label = input.required<string>();
  readonly checked = input(false);
  readonly mixed = input(false);
  readonly disabled = input(false);
  readonly hint = input<string | null>(null);
  /** The wanted value: `true` from mixed, otherwise the flip of `checked`. */
  readonly checkedChange = output<boolean>();

  protected readonly hintId = `sb-switch-hint-${nextId++}`;
  protected readonly ariaChecked = computed(() => (this.mixed() ? 'mixed' : String(this.checked())));

  protected toggle(): void {
    if (this.disabled()) return;
    this.checkedChange.emit(this.mixed() ? true : !this.checked());
  }
}
