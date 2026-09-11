import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

/**
 * A square correlation heatmap — spec v85 D38.
 *
 * A table rather than an SVG grid: the values are text that must stay
 * selectable and readable by a screen reader, and a `<table>` gives the row and
 * column headers for free. Colour bands the magnitude; the number is always
 * printed, because a heatmap you cannot read the value off is a picture.
 *
 * `clusters` are the bot's own groupings from `GET /risk`. A pair inside one
 * gets an outline *and* a title saying so — the outline alone would be a
 * colour-only cue.
 */
@Component({
  selector: 'sb-matrix',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="matrix scroll-x">
      <table>
        <thead>
          <tr>
            <th scope="col"></th>
            @for (label of labels(); track label) {
              <th scope="col">{{ label }}</th>
            }
          </tr>
        </thead>
        <tbody>
          @for (row of labels(); track row; let r = $index) {
            <tr>
              <th scope="row">{{ row }}</th>
              @for (col of labels(); track col; let c = $index) {
                <td
                  [class]="cellClass(r, c)"
                  [attr.title]="cellTitle(row, col, r, c)"
                >{{ cellText(r, c) }}</td>
              }
            </tr>
          }
        </tbody>
      </table>
    </div>
  `,
  styles: `
    .scroll-x { overflow-x: auto; }
    table { border-collapse: collapse; width: 100%; }
    th {
      font-size: var(--text-micro);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--text-faint);
      font-weight: 400;
      text-align: right;
      padding: 2px 6px;
      white-space: nowrap;
    }
    td {
      font-size: var(--text-micro);
      font-variant-numeric: tabular-nums;
      text-align: right;
      padding: 2px 6px;
      color: var(--text);
      white-space: nowrap;
    }
    .b1 { background: var(--quality-1); }
    .b2 { background: var(--quality-2); }
    .b3 { background: var(--quality-3); }
    .b4 { background: var(--quality-4); }
    .b5 { background: var(--quality-5); }
    .missing { color: var(--text-faint); background: none; }
    .clustered { outline: 1px solid var(--accent); outline-offset: -1px; }
  `,
})
export class Matrix {
  readonly labels = input.required<string[]>();
  readonly values = input.required<(number | null)[][]>();
  readonly clusters = input<string[][]>([]);

  /** Symbol → cluster index, so a cell lookup is O(1) rather than a scan. */
  private readonly clusterOf = computed(() => {
    const map = new Map<string, number>();
    this.clusters().forEach((group, i) => group.forEach((symbol) => map.set(symbol, i)));
    return map;
  });

  protected cellText(r: number, c: number): string {
    const v = this.values()[r]?.[c];
    return v === null || v === undefined ? '—' : v.toFixed(2);
  }

  protected cellClass(r: number, c: number): string {
    const v = this.values()[r]?.[c];
    if (v === null || v === undefined) return this.clustered(r, c) ? 'missing clustered' : 'missing';
    // Five bands over |ρ|, matching the five-step quality ramp the chips use.
    const band = Math.min(5, Math.max(1, Math.ceil(Math.abs(v) * 5) || 1));
    return this.clustered(r, c) ? `b${band} clustered` : `b${band}`;
  }

  protected cellTitle(row: string, col: string, r: number, c: number): string {
    const v = this.values()[r]?.[c];
    const base = v === null || v === undefined
      ? `${row} vs ${col}: not enough overlapping bars`
      : `${row} vs ${col}: ${v.toFixed(2)}`;
    return this.clustered(r, c) ? `${base} — same cluster, sized as one risk` : base;
  }

  private clustered(r: number, c: number): boolean {
    if (r === c) return false;
    const map = this.clusterOf();
    const a = map.get(this.labels()[r]);
    const b = map.get(this.labels()[c]);
    return a !== undefined && a === b;
  }
}
