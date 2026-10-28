import { describe, expect, it } from 'vitest';

import { LEG_HINT_TEXT, legLabel } from './leg-label';

describe('legLabel (v194 B3)', () => {
  it('labels nothing for a trade that never scaled out', () => {
    expect(legLabel({ leg_index: 0, leg_total: 1 })).toBeNull();
    expect(legLabel({ leg_index: 0, leg_total: 1, leg_exit_reason: 'stop' })).toBeNull();
  });

  it('labels each of two legs 1-based, with and without a reason', () => {
    expect(legLabel({ leg_index: 0, leg_total: 2 })).toBe('Leg 1 of 2');
    expect(legLabel({ leg_index: 0, leg_total: 2, leg_exit_reason: 'tp1' })).toBe('Leg 1 of 2 · TP1');
    expect(legLabel({ leg_index: 1, leg_total: 2, leg_exit_reason: 'stop' })).toBe('Leg 2 of 2 · Stop');
  });

  it('labels three legs, the reason in the trade page vocabulary', () => {
    expect(legLabel({ leg_index: 2, leg_total: 3 })).toBe('Leg 3 of 3');
    expect(legLabel({ leg_index: 2, leg_total: 3, leg_exit_reason: 'runner_trail' }))
      .toBe('Leg 3 of 3 · Runner trailed');
  });

  it('keeps an unmapped reason as recorded', () => {
    expect(legLabel({ leg_index: 1, leg_total: 2, leg_exit_reason: 'giveback' })).toBe('Leg 2 of 2 · giveback');
  });

  it('lets the label stand alone when no reason was recorded', () => {
    for (const reason of [null, undefined, '', '  ', 'other']) {
      expect(legLabel({ leg_index: 1, leg_total: 2, leg_exit_reason: reason })).toBe('Leg 2 of 2');
    }
  });

  it("reads a calendar row's exit_reason when there is no leg_exit_reason", () => {
    expect(legLabel({ leg_index: 0, leg_total: 2, exit_reason: 'tp1' })).toBe('Leg 1 of 2 · TP1');
    expect(legLabel({ leg_index: 0, leg_total: 2, exit_reason: 'other' })).toBe('Leg 1 of 2');
  });

  it("prefers the leg's own reason over a row-level one", () => {
    expect(legLabel({ leg_index: 0, leg_total: 2, leg_exit_reason: 'stop', exit_reason: 'tp1' }))
      .toBe('Leg 1 of 2 · Stop');
  });
});

describe('LEG_HINT_TEXT (v194 B3)', () => {
  it('says the rows are one plan, each its share, and that win rate and N count plans', () => {
    expect(LEG_HINT_TEXT).toContain('one plan');
    expect(LEG_HINT_TEXT).toContain("that part's share");
    expect(LEG_HINT_TEXT).toContain('Win rate and N count plans, not legs.');
  });

  it('does not name legs TP1 or Runner, since legs are numbered in close order', () => {
    expect(LEG_HINT_TEXT).not.toMatch(/TP1|Runner/);
    expect(LEG_HINT_TEXT).toContain('in the order they closed');
  });
});
