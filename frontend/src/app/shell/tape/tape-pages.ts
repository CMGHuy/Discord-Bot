/**
 * `sb-tape` shows whole tiles only: the strip never scrolls, so no symbol or
 * price is ever cut at the lane's edge (v179 layout audit). Tiles that do
 * not fit beside the others are not dropped for good -- the strip turns to
 * the next page every `TAPE_PAGE_SECONDS`, so the ticker still carries every
 * flagged symbol. A tile wider than the whole lane can never be shown whole,
 * so it is left out of every page (the lane at 768 is ~60px: nothing fits,
 * and the strip hides rather than show a sliver).
 */
export const TAPE_PAGE_SECONDS = 6;

/**
 * Greedy pages of whole tiles, as index lists, in order. A tile wider than
 * the lane is on no page; no page is ever empty. `gap` is the space the
 * layout puts between two neighbouring tiles.
 */
export function tapePages(widths: readonly number[], available: number, gap = 0): number[][] {
  const pages: number[][] = [];
  let used = 0;
  widths.forEach((width, index) => {
    if (width > available) return;
    const page = pages[pages.length - 1];
    const needed = used + (page ? gap : 0) + width;
    if (page && needed <= available) {
      page.push(index);
      used = needed;
    } else {
      pages.push([index]);
      used = width;
    }
  });
  return pages;
}
