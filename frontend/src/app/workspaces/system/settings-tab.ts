import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { SettingField } from '../../api/models';
import { SystemStore } from '../../stores/system.store';
import { Button } from '../../ui/button';
import { Checkbox, Select, SelectOption, TextInput } from '../../ui/form-controls';
import { dateTime } from '../../ui/format';
import { ControlRow, Panel } from '../../ui/layout';
import { FieldGroup, controlOf, groupByControl } from './settings-grouping';

/**
 * The settings form — rendered from the schema, with no field list anywhere.
 *
 * `GET /system/settings` ships `config.py`'s `Field` entries together with
 * their values, and this component walks them. **A new setting in
 * `config.py` must appear here with zero frontend change**; that property
 * exists in the Jinja UI and spec v14 Decision 8 forbids losing it. Any
 * `if (key === ...)` added below would quietly end it.
 *
 * The flow is preview → diff → save, in that order and not optional. The
 * diff comes from the same `settings_diff` the save runs, over the same
 * overlay, so what is approved is what is written.
 */
@Component({
  selector: 'sb-settings-tab',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Panel, Button, TextInput, Select, Checkbox, ControlRow],
  template: `
    @if (store.settingsStale()) {
      <!-- Spec v14 Decision 8: warn, do not silently reload. Another
           session saved (or a SIGHUP landed) while there are unsaved edits
           here. Reloading would discard configuration mid-sentence, and it
           is the kind of loss you notice only after pressing save. -->
      <p class="stale-form" role="alert">
        Settings changed elsewhere while you were editing. Your edits are
        untouched — save them, or
        <button sb-button variant="ghost" type="button" (click)="store.discardDraftAndReload()">
          discard and load the newer values
        </button>
      </p>
    }

    @if (store.settingsError(); as message) {
      <p class="form-error" role="status">{{ message }}</p>
    }

    <!-- SR56. Over a hundred fields had no way to find one by name. The
         controls sit above the form rather than in the save bar: they change
         what you are looking at, not what you are about to commit. -->
    <sb-control-row class="find" role="search">
      <sb-text-input
        label="Find a setting"
        type="text"
        [value]="store.settingsQuery()"
        (valueChange)="store.setSettingsQuery($event)"
      />
      <!-- topLabel is what lets the checkbox sit beside the labelled search
           input: both now have a label band above a 28px control band, so
           their boxes land on the same line. -->
      <sb-checkbox
        topLabel="Filter"
        label="Only changed from default"
        [checked]="store.onlyChanged()"
        (checkedChange)="store.setOnlyChanged($event)"
      />
      <span class="found">{{ foundLabel() }}</span>
    </sb-control-row>

    <!-- SR63. settings.html:101-103. The dot has meant this since SR56; the
         legend saying so is what makes it readable without guessing. -->
    <p class="legend"><span class="legend-dot"></span> = changed from default</p>

    @if (!store.visibleSections().length && !store.settingsEmpty()) {
      <p class="stale-form" role="status">
        No setting matches. Clear the search or the only-changed filter.
      </p>
    }

    @for (section of store.visibleSections(); track section.name) {
      <sb-panel [heading]="section.name">
        <!-- SR63. settings.html:115. -->
        <span class="field-count">{{ fieldCount(section.fields.length) }}</span>
        @if (section.description) {
          <p class="section-help">{{ section.description }}</p>
        }

        @for (group of groupsOf(section.fields); track group.kind) {
        <div class="fields" [class.compact]="group.kind === 'checkbox'">
          @for (field of group.fields; track field.key) {
            <div
              class="field"
              [class.changed]="isChanged(field)"
              [class.off-default]="store.differsFromDefault(field)"
            >
              <!-- The label band is empty because each control renders its own
                   label; it exists so all four rows of every cell map onto the
                   parent's four rows, which is what makes the subgrid align. -->
              <span class="band-label"></span>

              <div class="band-control">
              @switch (controlOf(field)) {
                @case ('checkbox') {
                  <sb-checkbox
                    [label]="field.label"
                    [checked]="boolValue(field)"
                    (checkedChange)="store.edit(field, $event)"
                  />
                }
                @case ('select') {
                  <sb-select
                    [label]="field.label"
                    [options]="optionsOf(field)"
                    [value]="textValue(field)"
                    (valueChange)="store.edit(field, $event)"
                  />
                }
                @default {
                  <sb-text-input
                    [label]="field.label"
                    [type]="inputTypeOf(field)"
                    [min]="field.min"
                    [max]="field.max"
                    [step]="field.step"
                    [value]="textValue(field)"
                    (valueChange)="store.edit(field, $event)"
                  />
                }
              }
              </div>

              <!-- Unguarded on purpose: an empty <p> collapses visually but
                   keeps the band count at four, and a missing band would shift
                   every later band of that cell up a row. -->
              <p class="help">{{ field.help }}</p>
              <p class="meta">
                <span class="key">{{ field.key }}</span>
                <!-- SR63. settings.html:50. Without it "what was this before I
                     touched it" has no answer on screen -- and the per-field
                     reset SR56 added is far less useful when you cannot see
                     what it will reset TO. -->
                @if (field.default) {
                  <span class="default-badge" title="Default value">{{ field.default }}</span>
                }
                @if (store.differsFromDefault(field)) {
                  <!-- The Jinja page's dot: differs from the CODE default,
                       which is a different statement from "edited just now"
                       and the one that survives a reload. -->
                  <button
                    sb-button
                    variant="ghost"
                    type="button"
                    class="reset"
                    [title]="'Reset to ' + field.default"
                    (click)="store.resetField(field)"
                  >
                    reset to default
                  </button>
                }
                @if (!field.hot_reloadable) {
                  <!-- Named per field rather than only in the diff: it is
                       the difference between a change that takes effect and
                       one that waits for a restart nobody knew to do. -->
                  <span class="restart">restart required</span>
                }
                @if (field.sensitive) {
                  <span class="secret">stored value hidden — type to replace</span>
                }
              </p>
            </div>
          }
        </div>
        }
      </sb-panel>
    }

    <!-- the save bar --------------------------------------------------- -->

    <sb-control-row class="bar">
      <span class="count">
        @if (store.dirty()) {
          {{ store.dirtyKeys().length }} changed
        } @else {
          No changes
        }
      </span>

      <sb-control-row class="bar-actions">
        <button
          sb-button
          variant="ghost"
          type="button"
          [disabled]="!store.dirty() || store.saving()"
          (click)="store.resetDraft()"
        >
          Discard
        </button>
        <button
          sb-button
          variant="secondary"
          type="button"
          [loading]="store.previewing()"
          [disabled]="!store.dirty()"
          (click)="store.previewChanges()"
        >
          Preview changes
        </button>
        <button
          sb-button
          variant="primary"
          type="button"
          [loading]="store.saving()"
          [disabled]="!store.awaitingSave()"
          (click)="store.save()"
        >
          Save
        </button>
      </sb-control-row>
    </sb-control-row>

    @if (store.formError(); as message) {
      <!-- The server validates against the schema this form was built from,
           so its message names the field and the bound it broke. Ours would
           be a worse copy. -->
      <p class="form-error" role="alert">{{ message }}</p>
    }

    @if (store.preview(); as diff) {
      <sb-panel heading="Pending changes">
        @if (diff.length) {
          <table class="diff">
            <thead>
              <tr><th>Setting</th><th>Now</th><th>After save</th></tr>
            </thead>
            <tbody>
              @for (row of diff; track row.key) {
                <tr>
                  <td>{{ row.label }}</td>
                  <!-- Already masked on both sides by the server for a
                       sensitive field, so a secret cannot reach the DOM
                       through the diff either. -->
                  <td class="old num">{{ row.old }}</td>
                  <td class="new num">{{ row.new }}</td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <!-- Reachable: blank on a field that already has a value counts
               as "no change" server-side, so an edit can diff to nothing. -->
          <p class="none">These edits change nothing on disk.</p>
        }

        @if (store.restartRequired().length) {
          <p class="restart-note">
            Needs a bot restart to take effect:
            {{ store.restartRequired().join(', ') }}
          </p>
        }
      </sb-panel>
    }

    @if (store.saved(); as saved) {
      <p class="saved" role="status">
        Saved {{ saved.diff.length }} change{{ saved.diff.length === 1 ? '' : 's' }}.
        @if (!saved.hot_reload.ok) {
          <!-- The write SUCCEEDED; only the signal telling the bot to
               re-read .env did not, which is routine outside Docker.
               Calling this a failure would tell the user their settings did
               not save when they did. -->
          <span class="hot-reload">
            The bot was not signalled — {{ saved.hot_reload.message }}
          </span>
        }
      </p>
    }

    <!-- audit, export, import ------------------------------------------ -->

    <sb-panel heading="Recent changes">
      @if (store.audit().length) {
        <ul class="audit">
          @for (entry of store.audit(); track entry.ts) {
            <li>
              <span class="audit-ts">{{ fmtDateTime(entry.ts) }}</span>
              <span class="audit-changes">
                @for (change of entry.changes; track change.key) {
                  <span class="audit-change">
                    {{ change.key }}: {{ change.old }} → {{ change.new }}
                  </span>
                }
              </span>
            </li>
          }
        </ul>
      } @else {
        <p class="none">No settings have been changed yet.</p>
      }
    </sb-panel>

    <sb-panel heading="Export and import">
      <p class="section-help">
        The export omits sensitive values entirely rather than masking them,
        so an exported file is safe to copy but cannot restore a credential.
      </p>
      <!-- A plain link, not a fetch: the browser then gets a Save dialog and
           the server's filename, both of which an XHR throws away. -->
      <a class="export" [href]="exportUrl" download>Download .env</a>
      <!-- SR63. settings.html:209. The asymmetry is the reason an exported
           file is safe to hand around, and it was nowhere on screen. -->
      <span class="asymmetry">
        Export omits credentials/tokens entirely; import accepts them.
      </span>

      <details class="import">
        <summary>Import from text or file</summary>
        <!-- SR56's fifth gap row. The file is read in the browser and its
             text goes through the SAME import endpoint as the textarea —
             no upload route, no second parser, and the user can see and
             edit what was read before committing it. -->
        <label class="import-file">
          <span>Choose a .env file</span>
          <input type="file" accept=".env,text/plain" (change)="onImportFile($event)" />
        </label>
        <textarea
          class="import-text"
          rows="6"
          [value]="importText()"
          (input)="importText.set($any($event.target).value)"
          placeholder="KEY=value, one per line — as exported."
        ></textarea>
        <sb-control-row class="import-actions">
          <button
            sb-button
            variant="secondary"
            type="button"
            [loading]="store.importing()"
            [disabled]="!importText().trim()"
            (click)="runImport()"
          >
            Import
          </button>
          @if (store.importMessage(); as message) {
            <span class="import-message">{{ message }}</span>
          }
        </sb-control-row>
      </details>
    </sb-panel>
  `,
  styles: `
    :host { display: grid; gap: var(--space-20); }

    .fields {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
      gap: var(--space-14);
      /* Between groups, against --space-14 between fields. The grouping is
         signposted by this gap and nothing else: sub-headings here would be
         widget-shape names ("Toggles", "Values") under a panel that already
         has a real one, and every section would carry three. */
      margin-bottom: var(--space-20);
    }
    /* A checkbox has no 260px-wide control to hold. */
    .compact { grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); }

    /* Four bands -- label, control, help, meta -- mapped onto four parent
       rows. The parent then sizes each band to the TALLEST cell across the
       row, so every control starts at the same y and every meta line bottoms
       out together, with the help text unclamped.
       Without subgrid the two requirements fight: fixed per-cell rows need
       the help clamped, and unclamped help puts every control at its own
       offset. */
    .field {
      grid-row: span 4;
      display: grid;
      grid-template-rows: subgrid;
      gap: var(--space-4);
      /* A CONSTANT gutter on every cell. Before this, .changed added a 2px
         border plus 8px of padding to edited fields only, so typing in a
         field shoved its contents 10px right of its neighbours -- the change
         marker was itself an alignment offender. */
      border-left: 2px solid transparent;
      padding-left: var(--space-8);
    }
    /* An edited field is marked so a change made three sections up is still
       findable without scrolling for it. */
    .changed { border-left-color: var(--accent); }
    .band-control { display: flex; align-items: flex-end; }

    /* -- SR63: badges and the legend --------------------------------- */
    .field-count {
      margin-left: var(--space-6);
      color: var(--text-faint);
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
    }
    .legend {
      margin-bottom: var(--space-8);
      color: var(--text-faint);
      font-size: var(--text-micro);
    }
    .legend-dot {
      display: inline-block;
      width: 6px;
      height: 6px;
      margin-right: var(--space-4);
      border-radius: 50%;
      background: var(--accent);
      vertical-align: middle;
    }
    .default-badge {
      color: var(--text-faint);
      font-family: var(--font-mono);
      font-size: var(--text-micro);
    }
    .asymmetry { color: var(--text-faint); font-size: var(--text-micro); }

    /* -- SR56: finding a setting ------------------------------------- */
    .find { margin-bottom: var(--space-10); }
    .find .found {
      margin-left: auto;
      color: var(--text-faint);
      font-size: var(--text-chip);
      font-variant-numeric: tabular-nums;
    }
    /* Away from the code default. Distinct from .changed, which is "edited
       in this draft" -- a field can be either, both, or neither. */
    .off-default .key::before {
      content: '';
      display: inline-block;
      width: 6px;
      height: 6px;
      margin-right: var(--space-4);
      border-radius: 50%;
      background: var(--accent);
      vertical-align: middle;
    }
    .import-file {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      margin-bottom: var(--space-8);
      color: var(--text-secondary);
      font-size: var(--text-chip);
    }

    .help { color: var(--text-muted); font-size: var(--text-chip); line-height: 1.4; }
    .meta { display: flex; flex-wrap: wrap; gap: var(--space-6); }
    .key {
      color: var(--text-faint);
      font-family: var(--font-mono);
      font-size: var(--text-chip);
    }
    .restart, .secret { color: var(--warn); font-size: var(--text-chip); }
    .secret { color: var(--text-faint); }

    /* No justify-content: space-between any more. It lived on the flex rule
       the primitive now owns, and .bar-actions' margin-left: auto states the
       same intent on the element that actually has to move. */
    .bar {
      padding: var(--space-10) var(--space-14);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      position: sticky;
      bottom: 0;
    }
    .count { color: var(--text-secondary); font-size: var(--text-table); }
    .bar-actions { margin-left: auto; }

    .stale-form {
      padding: var(--space-8) var(--space-14);
      border: 1px solid var(--warn);
      border-radius: var(--radius);
      color: var(--warn);
      font-size: var(--text-table);
    }
    .form-error { color: var(--neg); font-size: var(--text-table); }
    .saved { color: var(--text-secondary); font-size: var(--text-table); }
    .hot-reload { color: var(--warn); }

    .diff { width: 100%; border-collapse: collapse; font-size: var(--text-table); }
    .diff th {
      padding-bottom: var(--space-6);
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-align: left;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
    .diff td { padding: var(--space-4) var(--space-8) var(--space-4) 0; }
    .old { color: var(--text-muted); text-decoration: line-through; }
    .new { color: var(--text); }
    .restart-note { margin-top: var(--space-10); color: var(--warn); font-size: var(--text-table); }

    .audit { display: grid; gap: var(--space-6); font-size: var(--text-table); }
    .audit li { display: flex; gap: var(--space-10); }
    .audit-ts { color: var(--text-faint); white-space: nowrap; }
    .audit-changes { display: grid; gap: var(--space-4); }
    .audit-change { color: var(--text-secondary); font-family: var(--font-mono); font-size: var(--text-chip); }

    .none { color: var(--text-faint); font-size: var(--text-table); }

    .export { color: var(--accent); font-size: var(--text-table); text-decoration: none; }
    .export:hover { text-decoration: underline; }
    .import { margin-top: var(--space-14); font-size: var(--text-table); }
    summary { color: var(--text-secondary); cursor: pointer; }
    .import-text {
      width: 100%;
      margin-top: var(--space-8);
      padding: var(--space-8);
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font-family: var(--font-mono);
      font-size: var(--text-chip);
      resize: vertical;
    }
    .import-actions { margin-top: var(--space-8); }
    .import-message { color: var(--text-secondary); }
  `,
})
export class SettingsTab {
  protected readonly store = inject(SystemStore);

  /** Through the store, not by injecting `ApiClient`: components read
   *  stores, and one exception is how "the component can fetch" starts. */
  protected readonly exportUrl = this.store.exportUrl();

  protected readonly importText = signal('');

  protected readonly fmtDateTime = dateTime;

  /** Which control a field gets, and a section's fields partitioned by it.
   *  Both live in `settings-grouping.ts` so they are pure functions with
   *  their own tests rather than methods on a 585-line component. */
  protected readonly groupsOf = groupByControl;
  protected readonly controlOf = controlOf;

  protected inputTypeOf(field: SettingField): 'text' | 'number' | 'password' {
    if (field.sensitive || field.type === 'password') return 'password';
    return field.type === 'number' || field.type === 'float' ? 'number' : 'text';
  }

  /** The server ships `[{value, label}]`, typed `unknown[]` because the
   *  shape is `config.py`'s to decide. Narrowed here rather than trusted, so
   *  a changed shape renders nothing instead of `[object Object]`. */
  protected optionsOf(field: SettingField): SelectOption[] {
    return field.options
      .filter((option): option is Record<string, unknown> =>
        typeof option === 'object' && option !== null,
      )
      .map((option) => ({
        value: String(option['value'] ?? ''),
        label: String(option['label'] ?? option['value'] ?? ''),
      }));
  }

  protected textValue(field: SettingField): string {
    const value = this.store.currentValue(field);
    return typeof value === 'boolean' ? String(value) : value;
  }

  protected boolValue(field: SettingField): boolean {
    return this.store.currentValue(field) === true;
  }

  /** Edited in THIS draft — deliberately a different question from
   *  `store.differsFromDefault`, which asks whether the value is away from
   *  the code default. Both are shown, by different marks. */
  protected isChanged(field: SettingField): boolean {
    return field.key in this.store.draft();
  }

  /** How much of the form the current filters are showing. Worth stating:
   *  "3 of 118" is the difference between a narrow search and a filter that
   *  has accidentally hidden the setting being looked for. */
  protected readonly foundLabel = computed(() => {
    const shown = this.store.visibleFields().length;
    const total = this.store.fields().length;
    return shown === total ? `${total} settings` : `${shown} of ${total}`;
  });

  /** SR63. settings.html:115 -- pluralised, because "1 fields" is the kind
   *  of detail that makes a page look unfinished. */
  protected fieldCount(n: number): string {
    return `${n} field${n === 1 ? '' : 's'}`;
  }

  protected runImport(): void {
    this.store.importSettings(this.importText());
    this.importText.set('');
  }

  /**
   * SR56 — read a chosen `.env` into the textarea rather than importing it
   * straight away.
   *
   * Deliberately NOT a one-click import: this endpoint rewrites the whole
   * configuration, and a mis-clicked file would do it silently. Landing the
   * contents in the box means the same Import button, the same preview, and
   * a chance to see what is about to be applied.
   */
  protected onImportFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    file.text().then((text) => this.importText.set(text));
    // Cleared so choosing the SAME file again still fires a change event.
    input.value = '';
  }
}
