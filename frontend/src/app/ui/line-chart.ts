export interface LineChartPoint {
  date: string;
  value: number;
}

export interface LineChartSeries {
  name: string;
  points: LineChartPoint[];
}

/** Maps an ISO date string to 0-1, linear in TIME, not in array index --
 *  unevenly-spaced dates (a weekly rolling-return point beside a monthly
 *  calendar-return one) must not be drawn as if they were evenly spaced. */
export function lineChartXScale(dates: readonly string[]): (date: string) => number {
  const times = dates.map((d) => new Date(d).getTime());
  const min = Math.min(...times);
  const max = Math.max(...times);
  const span = max - min;
  return (date: string) => (span === 0 ? 0 : (new Date(date).getTime() - min) / span);
}

/** Maps a value to 0-1. An explicit `domain` (e.g. a fixed 0-100 win-rate
 *  axis) wins over the auto min/max of `values` -- see the Calibration
 *  decile chart, which needs an ABSOLUTE scale so an 80% reference line
 *  means the same thing regardless of which decile happens to be tallest. */
export function lineChartYScale(
  values: readonly number[],
  domain?: { min: number; max: number },
): (value: number) => number {
  const min = domain?.min ?? Math.min(...values);
  const max = domain?.max ?? Math.max(...values);
  const span = max - min;
  // A flat series has no range to scale into. Drawn at the middle rather
  // than the top or bottom, where it would read as an extreme -- same rule
  // sparkline.ts's y() already applies.
  return (value: number) => (span === 0 ? 0.5 : (value - min) / span);
}

/** One series' SVG path, in a 0-1 x 0-1 coordinate space the component
 *  scales into its actual viewBox. */
export function seriesPath(
  series: LineChartSeries,
  xScale: (date: string) => number,
  yScale: (value: number) => number,
): string {
  const points = series.points;
  if (points.length === 0) return '';
  if (points.length === 1) {
    const x = xScale(points[0].date);
    const y = 1 - yScale(points[0].value);
    return `M ${x.toFixed(4)} ${y.toFixed(4)}`;
  }
  return points
    .map((p, i) => {
      const x = xScale(p.date).toFixed(4);
      const y = (1 - yScale(p.value)).toFixed(4); // SVG y grows downward
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');
}
