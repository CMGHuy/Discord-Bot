import { ChangeDetectionStrategy, Component, ElementRef, computed, input, model, viewChildren } from '@angular/core';

/** One choice in a segmented control. */
export interface SegmentOption { value: string; label: string; count?: number; }

/** A single-select toggle with roving tabindex and arrow-key navigation. */
@Component({
  selector: 'sb-segmented', changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="track" role="group" [attr.aria-label]="label()" (keydown)="onKeydown($event)">
      @for (option of options(); track option.value; let i = $index) {
        <button #segment type="button" class="segment" [class.current]="option.value === value()"
          [attr.aria-pressed]="option.value === value()" [tabindex]="i === focusIndex() ? 0 : -1" (click)="value.set(option.value)">
          {{ option.label }} @if (option.count !== undefined) { <span class="count num">{{ option.count }}</span> }
        </button>
      }
    </div>`,
  styles: `
    :host { display: block; min-width: 0; max-width: 100%; }
    .track { display: inline-flex; max-width: 100%; overflow-x: auto; scrollbar-width: thin; border: 1px solid var(--border-strong); border-radius: var(--radius); }
    .segment { flex: 0 0 auto; display: inline-flex; align-items: center; gap: var(--space-6); min-height: var(--control-h); padding: 0 var(--space-10); background: transparent; border: 0; border-left: 1px solid var(--border); color: var(--text-secondary); font: inherit; font-size: var(--text-table); font-weight: 500; white-space: nowrap; cursor: pointer; transition: color var(--transition), background var(--transition); }
    .segment:first-child { border-left: 0; } .segment:hover { color: var(--text); }
    .segment:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .current { background: var(--accent-soft); color: var(--text); }
    .count { color: var(--text-muted); font-size: var(--text-chip); }
  `,
})
export class Segmented {
  readonly options = input.required<SegmentOption[]>(); readonly label = input.required<string>(); readonly value = model<string>('');
  private readonly segments = viewChildren<ElementRef<HTMLButtonElement>>('segment');
  protected readonly focusIndex = computed(() => Math.max(0, this.options().findIndex((option) => option.value === this.value())));
  protected onKeydown(event: KeyboardEvent): void {
    const options = this.options(); if (!options.length) return;
    const last = options.length - 1; const current = this.focusIndex();
    const next = event.key === 'ArrowRight' || event.key === 'ArrowDown' ? (current === last ? 0 : current + 1)
      : event.key === 'ArrowLeft' || event.key === 'ArrowUp' ? (current === 0 ? last : current - 1)
      : event.key === 'Home' ? 0 : event.key === 'End' ? last : -1;
    if (next < 0) return; event.preventDefault(); this.value.set(options[next].value); this.segments()[next]?.nativeElement.focus();
  }
}
