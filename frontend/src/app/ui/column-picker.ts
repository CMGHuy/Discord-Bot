import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { PreferencesStore } from '../stores/preferences.store';
import { Density } from './data-table/data-table.types';
import { clearTableColumns, writeTableColumns } from './table-prefs';

/** The minimum a column needs to appear in the picker. `ColumnDef` satisfies
 *  it, so a call site passes the same array it gives the table. */
export interface PickableColumn {
  key: string;
  header: string;
}

/**
 * Chooses which columns a table shows — spec v14's `ColumnPickerComponent`.
 *
 * Three constraints, enforced structurally rather than by review discipline:
 *
 *  1. **"Reset to default" is always present**, and `defaults` is a distinct
 *     input from `visible`. The designed column set is a first-class thing the
 *     component knows, not the first entry in a list of presets — so there is
 *     always one click back to what the table was designed to look like.
 *  2. **Visibility only.** No ordering affordance exists here and no ordering
 *     input exists on the table, so the drag-to-reorder behaviour that was
 *     removed cannot return through this component.
 *  3. **Persists per user, keyed by table id**, through `PreferencesStore` —
 *     server-side, so the same person sees the same columns on a laptop and a
 *     desktop.
 *
 * Ownership of that persistence is split on purpose, and the split is the
 * thing to understand before changing this file: **this component writes, the
 * workspace reads.** Mutations all originate here, so `setColumns` and
 * `resetColumns` live here. The initial value is read once by the workspace
 * (`prefs.columns(tableId) ?? DEFAULT_COLUMNS`) because the workspace owns the
 * signal the table binds to. Having both read would give one piece of state
 * two owners and a load order to get wrong.
 */
@Component({
  selector: 'sb-column-picker',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="picker">
      <button
        type="button"
        class="trigger"
        [attr.aria-expanded]="open()"
        aria-haspopup="true"
        (click)="open.set(!open())"
      >
        Columns
        <span class="count num">{{ visible().length }}/{{ columns().length }}</span>
      </button>

      @if (open()) {
        <div class="panel" role="group" aria-label="Visible columns">
          <ul>
            @for (column of pickable(); track column.key) {
              <li>
                <label [class.locked]="isLast(column.key)">
                  <input
                    type="checkbox"
                    [checked]="isVisible(column.key)"
                    [disabled]="isLast(column.key)"
                    (change)="toggle(column.key)"
                  />
                  <span>{{ column.header || column.key }}</span>
                </label>
              </li>
            }
          </ul>
          <button type="button" class="reset" (click)="reset()">Reset to default</button>
        </div>
      }
    </div>
  `,
  styles: `
    .picker { position: relative; display: inline-block; }

    .trigger {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      padding: var(--space-4) var(--space-10);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: border-color var(--transition);
    }
    .trigger:hover { border-color: var(--border-strong); }
    .trigger:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    .count { color: var(--text-muted); font-size: var(--text-chip); }

    .panel {
      position: absolute;
      right: 0;
      z-index: 10;
      min-width: 200px;
      margin-top: var(--space-4);
      padding: var(--space-8);
      background: var(--surface-raised);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius);
      box-shadow: 0 6px 24px rgb(0 0 0 / 0.5);
    }
    ul { list-style: none; }
    label {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      padding: var(--space-4) var(--space-6);
      font-size: var(--text-table);
      cursor: pointer;
    }
    label:hover { background: var(--surface); }
    /* The last visible column cannot be unchecked: an empty table is not a
       column preference, it is a broken screen with no way back except this
       same menu. */
    label.locked { color: var(--text-faint); cursor: default; }

    .reset {
      width: 100%;
      margin-top: var(--space-6);
      padding: var(--space-6);
      background: none;
      border: 0;
      border-top: 1px solid var(--border);
      color: var(--accent);
      font: inherit;
      font-size: var(--text-table);
      text-align: left;
      cursor: pointer;
    }
    .reset:hover { background: var(--surface); }
    .reset:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
  `,
})
export class ColumnPickerComponent {
  private readonly preferences = inject(PreferencesStore);

  /** Persistence key. Must be stable across releases — it is what a saved
   *  preference is filed under. */
  readonly tableId = input.required<string>();
  /** Every column the table can show, in the table's render order. */
  readonly columns = input.required<PickableColumn[]>();
  /** The designed set, and what "Reset to default" restores. Distinct from
   *  `visible` so the design is never merely the current state. */
  readonly defaults = input.required<string[]>();
  /** The current set, in render order. SR14 made the order meaningful, so
   *  toggling preserves it rather than re-deriving from `columns`. */
  readonly visible = input.required<string[]>();
  /** Which density this edit applies to. The two are stored separately, so
   *  arranging Compact must leave Full exactly as it was. */
  readonly density = input.required<Density>();
  /** Columns the table pins — row actions, the expander. They are not the
   *  user's to hide, so they never appear in the list at all rather than
   *  appearing disabled: an unexplained disabled checkbox reads as a bug. */
  readonly pinned = input<string[]>([]);

  readonly visibleChange = output<string[]>();

  protected readonly open = signal(false);

  private readonly visibleSet = computed(() => new Set(this.visible()));
  private readonly pinnedSet = computed(() => new Set(this.pinned()));

  /** What the picker offers: everything the table can show, minus the pins. */
  protected readonly pickable = computed(() =>
    this.columns().filter((column) => !this.pinnedSet().has(column.key)),
  );

  protected isVisible(key: string): boolean {
    return this.visibleSet().has(key);
  }

  protected isLast(key: string): boolean {
    return this.isVisible(key) && this.visible().length === 1;
  }

  protected toggle(key: string): void {
    const next = new Set(this.visibleSet());
    if (next.has(key)) {
      if (next.size === 1) return;
      next.delete(key);
    } else {
      next.add(key);
    }
    // Keep the user's arrangement. Re-deriving from `columns` would silently
    // undo a drag-reorder every time a column was toggled -- the order is
    // meaningful since SR14, so the previously-visible keys keep their
    // positions and a newly-shown one goes where the table would put it.
    const kept = this.visible().filter((columnKey) => next.has(columnKey));
    const added = this.columns()
      .map((column) => column.key)
      .filter((columnKey) => next.has(columnKey) && !kept.includes(columnKey));
    const ordered = [...kept, ...added];

    this.preferences.update((prefs) =>
      writeTableColumns(prefs, this.tableId(), this.density(), ordered),
    );
    this.visibleChange.emit(ordered);
  }

  protected reset(): void {
    // Forgets the preference rather than storing the defaults as a choice, so
    // a table whose designed columns change later picks the new ones up --
    // and only for THIS density, so resetting Compact leaves Full arranged.
    this.preferences.update((prefs) =>
      clearTableColumns(prefs, this.tableId(), this.density()),
    );
    this.visibleChange.emit([...this.defaults()]);
  }
}
