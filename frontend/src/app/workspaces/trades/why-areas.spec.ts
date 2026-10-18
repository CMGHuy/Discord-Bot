import { describe, expect, it } from 'vitest';
import { areaStyle, OVERVIEW_AREAS, WHY_CARDS, whyAreas } from './why-areas';

describe('trade card area maps', () => {
  it('preserves the full reading order and responsive maps', () => {
    expect(WHY_CARDS).toEqual(['why', 'scores', 'sources', 'breakdown', 'gates', 'context']);
    expect(whyAreas(new Set(WHY_CARDS))).toEqual({
      one: '"why" "scores" "sources" "breakdown" "gates" "context"',
      two: '"why why" "scores context" "sources sources" "breakdown breakdown" "gates gates"',
      three: '"why why scores" "sources sources sources" "breakdown breakdown breakdown" "gates gates context"',
    });
    expect(OVERVIEW_AREAS).toEqual({ one: '"plan" "position" "outcome"', two: '"plan position" "outcome outcome"', three: '"plan position outcome"' });
    expect(areaStyle(OVERVIEW_AREAS)).toEqual({ '--areas-1': OVERVIEW_AREAS.one, '--areas-2': OVERVIEW_AREAS.two, '--areas-3': OVERVIEW_AREAS.three });
  });
  for (let mask = 0; mask < 64; mask++) {
    it(`fills rows and includes precisely the present cards for subset ${mask}`, () => {
      const present = new Set(WHY_CARDS.filter((_, index) => mask & (1 << index)));
      const areas = whyAreas(present);
      for (const [key, width] of [['one', 1], ['two', 2], ['three', 3]] as const) {
        if (!present.size) { expect(areas[key]).toBe('none'); continue; }
        const rows = [...areas[key].matchAll(/"([^"]+)"/g)].map(match => match[1].split(' '));
        expect(rows.length).toBeGreaterThan(0);
        expect(new Set(rows.flat())).toEqual(present);
        for (const row of rows) expect(row.length).toBe(width);
        for (const card of present) expect(rows.filter(row => row.includes(card))).toHaveLength(1);
      }
    });
  }
  it('widens surviving row partners', () => {
    expect(whyAreas(new Set(['why', 'context'])).three).toBe('"why why why" "context context context"');
    expect(whyAreas(new Set(['scores', 'context'])).three).toBe('"scores scores scores" "context context context"');
    expect(whyAreas(new Set(['why', 'context'])).two).toBe('"why why" "context context"');
    expect(whyAreas(new Set(['gates'])).three).toBe('"gates gates gates"');
  });
});
