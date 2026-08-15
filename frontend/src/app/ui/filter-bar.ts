import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import { Button } from './button';
import { ControlRow } from './layout';

/** One choice in a filter chip row. */
export interface FilterChip {
  value: string;
  label: string;
  /** Shown beside the label when the store knows the count. */
  count?: number;
}

/**
 * The row of filter controls above a table.
 *
 * `activeCount` and "Clear all" are the reason this is a component rather than
 * a `<div>`: a filtered table that looks like an empty one is the single most
 * common way a list tool wastes someone's afternoon, so the bar always states
 * how many filters are on and always offers one click to remove them.
 *
 * Controls are projected, so a workspace composes its own `Select`s and
 * `TextInput`s here rather than this component growing a filter schema.
 */
@Component({
  selector: 'sb-filter-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, ControlRow],
  template: `
    <sb-control-row>
      <ng-content />

      @if (activeCount() > 0) {
        <span class="active num">{{ activeCount() }} active</span>
        <button sb-button variant="ghost" type="button" (click)="cleared.emit()">
          Clear all
        </button>
      }
    </sb-control-row>
  `,
  styles: `
    :host { display: block; padding: var(--space-10) 0; }
    .active { margin-left: auto; color: var(--text-secondary); font-size: var(--text-table); }
  `,
})
export class FilterBar {
  readonly activeCount = input(0);
  readonly cleared = output<void>();
}

/**
 * A single-select chip row — Trades' status filter.
 *
 * **Chips, not tabs**, and the distinction is deliberate: tabs over statuses
 * would reintroduce the "separate page per state" model that collapsing Plans,
 * Journal and the dashboard tables into one Trades workspace exists to
 * abolish. A chip row reads as "narrow this list", which is what it does.
 *
 * `null` is the unfiltered state and is always reachable through the leading
 * "All" chip, so there is no way to get stuck inside a filter.
 */
@Component({
  selector: 'sb-filter-chips',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="chips" role="group" [attr.aria-label]="label()">
      <button
        type="button"
        class="chip"
        [class.active]="selected() === null"
        [attr.aria-pressed]="selected() === null"
        (click)="selectedChange.emit(null)"
      >
        {{ allLabel() }}
      </button>

      @for (chip of chips(); track chip.value) {
        <button
          type="button"
          class="chip"
          [class.active]="chip.value === selected()"
          [attr.aria-pressed]="chip.value === selected()"
          (click)="selectedChange.emit(chip.value)"
        >
          {{ chip.label }}
          @if (chip.count !== undefined) {
            <span class="count num">{{ chip.count }}</span>
          }
        </button>
      }
    </div>
  `,
  styles: `
    .chips { display: flex; gap: var(--space-4); flex-wrap: wrap; }
    .chip {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      padding: var(--space-4) var(--space-10);
      background: transparent;
      border: 1px solid var(--border);
      border-radius: var(--radius-chip);
      color: var(--text-secondary);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: color var(--transition), border-color var(--transition);
    }
    .chip:hover { color: var(--text); border-color: var(--border-strong); }
    .chip:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
    /* Selection is interactive state, which is what blue is for. */
    .active { color: var(--text); border-color: var(--accent); background: var(--surface-raised); }
    .count { color: var(--text-muted); font-size: var(--text-chip); }
  `,
})
export class FilterChips {
  readonly chips = input.required<FilterChip[]>();
  readonly selected = input<string | null>(null);
  readonly label = input('Filter');
  readonly allLabel = input('All');

  readonly selectedChange = output<string | null>();
}
