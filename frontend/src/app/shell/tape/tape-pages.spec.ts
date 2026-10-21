import { TAPE_PAGE_SECONDS, tapePages } from './tape-pages';

describe('tapePages', () => {
  it('puts every tile on one page when they all fit', () => {
    expect(tapePages([100, 100, 100], 300)).toEqual([[0, 1, 2]]);
  });

  it('starts a new page before a tile would cross the edge, keeping the order', () => {
    expect(tapePages([100, 100, 100, 100, 100], 250)).toEqual([[0, 1], [2, 3], [4]]);
  });

  it('counts the gap between neighbours but not before the first tile', () => {
    expect(tapePages([100, 100], 205, 5)).toEqual([[0, 1]]);
    expect(tapePages([100, 100], 205, 5.5)).toEqual([[0], [1]]);
  });

  it('leaves a tile wider than the whole lane on no page, since it can never be shown whole', () => {
    expect(tapePages([80, 400, 80], 250)).toEqual([[0, 2]]);
    expect(tapePages([300, 400], 250)).toEqual([]);
  });

  it('has no pages for no tiles, and turns every few seconds', () => {
    expect(tapePages([], 250)).toEqual([]);
    expect(TAPE_PAGE_SECONDS).toBeGreaterThanOrEqual(4);
  });
});
