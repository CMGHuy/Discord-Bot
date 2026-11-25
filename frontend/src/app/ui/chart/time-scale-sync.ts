import type { IChartApi, LogicalRange, LogicalRangeChangeEventHandler } from 'lightweight-charts';

/** Logical ranges are fractional bar indices; closer than this is the same view. */
const SAME_RANGE_EPSILON = 1e-6;

function sameRange(a: LogicalRange | null, b: LogicalRange): boolean {
  return a !== null && Math.abs(a.from - b.from) < SAME_RANGE_EPSILON && Math.abs(a.to - b.to) < SAME_RANGE_EPSILON;
}

/**
 * v246 §A3 "Linked scrolling". lightweight-charts 5 has no shared time
 * scale, so every registered chart follows the others' visible logical
 * range. Two guards keep it from ping-ponging: `following` swallows the
 * echo a follower reports while the source's handler is still running, and
 * `sameRange` swallows an echo that arrives later, when the source already
 * shows that range. Charts in one group must share their bars (the same
 * days), or one logical range means different dates on each.
 */
export class TimeScaleSync {
  private readonly handlers = new Map<IChartApi, LogicalRangeChangeEventHandler>();
  private following = false;

  /** Joins `chart` to the group; the returned function leaves it (safe to call twice). */
  register(chart: IChartApi): () => void {
    let handler = this.handlers.get(chart);
    if (!handler) {
      handler = (range) => this.follow(chart, range);
      this.handlers.set(chart, handler);
      chart.timeScale().subscribeVisibleLogicalRangeChange(handler);
    }
    const subscription = handler;
    return () => {
      if (this.handlers.get(chart) !== subscription) return;
      this.handlers.delete(chart);
      chart.timeScale().unsubscribeVisibleLogicalRangeChange(subscription);
    };
  }

  private follow(source: IChartApi, range: LogicalRange | null): void {
    if (this.following || range === null) return;
    this.following = true;
    try {
      for (const chart of this.handlers.keys()) {
        if (chart !== source && !sameRange(chart.timeScale().getVisibleLogicalRange(), range)) {
          chart.timeScale().setVisibleLogicalRange(range);
        }
      }
    } finally {
      this.following = false;
    }
  }
}
