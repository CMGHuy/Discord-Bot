/**
 * Month-grid geometry. Pure string/number math, no store and no HTTP, so
 * the awkward parts -- leap years, a month starting on a Sunday, the
 * December/January boundary -- are testable without standing anything up.
 *
 * `Date` is used only as a calendar oracle (how long is this month, what
 * weekday is the 1st). Every value that leaves this module is a
 * `YYYY-MM-DD` string, because that is the key the API's `days` array uses
 * and a `Date` round-trip through a timezone is exactly how a grid ends up
 * one day out.
 */

export interface GridCell {
  /** `YYYY-MM-DD`, zero-padded to match the API's day keys byte for byte. */
  date: string;
  dayOfMonth: number;
  /** False for the leading/trailing days borrowed from adjacent months. */
  inMonth: boolean;
  /** Saturday or Sunday. No trade ever closes on one, so the grid renders
   *  these inert rather than as an empty-but-clickable trading day. */
  weekend: boolean;
}

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

function iso(year: number, month: number, day: number): string {
  const mm = `${month}`.padStart(2, '0');
  const dd = `${day}`.padStart(2, '0');
  return `${year}-${mm}-${dd}`;
}

/**
 * Whole weeks covering `month` (`YYYY-MM`), Monday first.
 *
 * Always full rows of seven: the leading and trailing cells come from the
 * adjacent months, flagged `inMonth: false`. A short final row would make
 * the grid's last week a different width from the rest.
 */
export function monthMatrix(month: string): GridCell[][] {
  const [year, index] = month.split('-').map(Number);

  // Day 0 of the next month is the last day of this one -- the standard
  // trick, and the reason leap years need no special case here.
  const daysInMonth = new Date(year, index, 0).getDate();

  // getDay() is Sunday-0; the grid is Monday-first, so Sunday becomes 6.
  const firstWeekday = (new Date(year, index - 1, 1).getDay() + 6) % 7;

  const weeks: GridCell[][] = [];
  let week: GridCell[] = [];

  const push = (offset: number) => {
    // `new Date(year, index - 1, offset)` normalises out of range in both
    // directions, so offset 0 is the previous month's last day and
    // daysInMonth + 1 is the next month's first.
    const d = new Date(year, index - 1, offset);
    const cellMonth = d.getMonth() + 1;
    const weekday = d.getDay();
    week.push({
      date: iso(d.getFullYear(), cellMonth, d.getDate()),
      dayOfMonth: d.getDate(),
      inMonth: cellMonth === index && d.getFullYear() === year,
      weekend: weekday === 0 || weekday === 6,
    });
    if (week.length === 7) {
      weeks.push(week);
      week = [];
    }
  };

  for (let offset = 1 - firstWeekday; offset <= daysInMonth; offset += 1) push(offset);
  // Fill the final row out to seven.
  for (let offset = daysInMonth + 1; week.length > 0; offset += 1) push(offset);

  return weeks;
}

/** `"2026-08"` -> `"August 2026"`. */
export function monthLabel(month: string): string {
  const [year, index] = month.split('-').map(Number);
  return `${MONTH_NAMES[index - 1]} ${year}`;
}
