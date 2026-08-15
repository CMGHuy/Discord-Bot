import { describe, expect, it } from 'vitest';

import { SettingField } from '../../api/models';
import { controlOf, groupByControl } from './settings-grouping';

function field(key: string, type: string): SettingField {
  return { key, label: key, type, value: '', default: '', help: '',
           options: [], sensitive: false, hot_reloadable: true,
           min: null, max: null, step: null } as unknown as SettingField;
}

describe('groupByControl', () => {
  it('orders groups checkboxes, selects, then inputs', () => {
    const groups = groupByControl([
      field('a_text', 'string'),
      field('b_flag', 'checkbox'),
      field('c_mode', 'select'),
    ]);
    expect(groups.map((g) => g.kind)).toEqual(['checkbox', 'select', 'input']);
  });

  it('preserves schema order inside a group', () => {
    const groups = groupByControl([
      field('z_flag', 'checkbox'),
      field('a_flag', 'checkbox'),
    ]);
    expect(groups[0].fields.map((f) => f.key)).toEqual(['z_flag', 'a_flag']);
  });

  it('omits a group with no fields rather than emitting an empty one', () => {
    const groups = groupByControl([field('only', 'checkbox')]);
    expect(groups).toHaveLength(1);
    expect(groups[0].kind).toBe('checkbox');
  });

  it('treats every non-checkbox, non-select type as an input', () => {
    for (const type of ['string', 'number', 'float', 'password']) {
      expect(controlOf(field('k', type))).toBe('input');
    }
  });

  it('returns nothing for an empty section', () => {
    expect(groupByControl([])).toEqual([]);
  });
});
