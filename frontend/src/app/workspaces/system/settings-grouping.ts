import { SettingField } from '../../api/models';

/**
 * Which control a field gets, and how a section's fields are grouped by it.
 *
 * Extracted from `settings-tab.ts` so the partition is a pure function with
 * its own tests, rather than a computed buried in a 585-line component.
 *
 * **The mapping is by `type` alone, never by key.** `GET /system/settings`
 * ships `config.py`'s schema and this form renders whatever arrives, so a new
 * setting appears with zero frontend change (spec v14 Decision 8). An
 * `if (key === …)` anywhere in this file would quietly end that property.
 */
export type ControlKind = 'checkbox' | 'select' | 'input';

export function controlOf(field: SettingField): ControlKind {
  if (field.type === 'checkbox') return 'checkbox';
  if (field.type === 'select') return 'select';
  return 'input';
}

export interface FieldGroup {
  kind: ControlKind;
  fields: SettingField[];
}

/**
 * A section's fields, partitioned by control type.
 *
 * Checkboxes first, then selects, then text and number inputs: shortest cells
 * to tallest, so the most variable cells sink to the bottom of the panel and
 * the eye gets a compact block of toggles at the top.
 *
 * **Stable within a group** — `config.py`'s declaration order survives, so
 * settings written next to each other stay next to each other. A sort here
 * would scatter them alphabetically and lose the author's grouping.
 *
 * An empty group is omitted rather than emitted, so the template never has to
 * guard against rendering a header-less run of nothing.
 */
const ORDER: ControlKind[] = ['checkbox', 'select', 'input'];

export function groupByControl(fields: SettingField[]): FieldGroup[] {
  return ORDER.map((kind) => ({
    kind,
    fields: fields.filter((field) => controlOf(field) === kind),
  })).filter((group) => group.fields.length > 0);
}
