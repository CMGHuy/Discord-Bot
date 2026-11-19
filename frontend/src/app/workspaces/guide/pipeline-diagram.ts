import { ChangeDetectionStrategy, Component, ElementRef, computed, inject } from '@angular/core';

import { GuideStore } from '../../stores/guide.store';
import { ViewportService } from '../../ui/breakpoints';
import { chartWidth } from '../../ui/chart/chart-width';

const VIEWBOX_W = 680;
const BOX_W = 140;
const BOX_H = 52;
const LINE_GAP = 16;
const COLS = [10, 180, 350, 520] as const;
const ROWS = [10, 110, 210] as const;

export interface PipelineStage { label: string; lines: readonly string[]; slug: string }

/** Spec v215 chapter 3: watchlist to close, each with the chapter that explains it. */
export const PIPELINE_STAGES: readonly PipelineStage[] = [
  { label: 'Watchlist', lines: ['Watchlist'], slug: 'admin-tour' },
  { label: 'Price data', lines: ['Price data'], slug: 'levels' },
  { label: 'Levels from every method', lines: ['Levels from', 'every method'], slug: 'levels' },
  { label: 'Duplicate merge', lines: ['Duplicate', 'merge'], slug: 'levels' },
  { label: 'Strategy signals', lines: ['Strategy', 'signals'], slug: 'strategies' },
  { label: 'Gates', lines: ['Gates'], slug: 'gates' },
  { label: 'Plan construction', lines: ['Plan', 'construction'], slug: 'trade-plan' },
  { label: 'Sizing and caps', lines: ['Sizing', 'and caps'], slug: 'sizing-risk' },
  { label: 'Alert', lines: ['Alert'], slug: 'reading-an-alert' },
  { label: 'Monitoring', lines: ['Monitoring'], slug: 'after-the-alert' },
  { label: 'Close', lines: ['Close'], slug: 'after-the-alert' },
];

interface Point { x: number; y: number }
interface Edge { x1: number; y1: number; x2: number; y2: number }

/** Snake layout: rows of four, the middle row right to left. */
function place(index: number): Point {
  const row = Math.floor(index / 4);
  const step = index % 4;
  return { x: COLS[row % 2 === 1 ? 3 - step : step], y: ROWS[row] };
}

function edge(a: Point, b: Point): Edge {
  if (a.y !== b.y) return { x1: a.x + BOX_W / 2, y1: a.y + BOX_H, x2: b.x + BOX_W / 2, y2: b.y - 2 };
  const y = a.y + BOX_H / 2;
  return b.x > a.x ? { x1: a.x + BOX_W, y1: y, x2: b.x - 2, y2: y } : { x1: a.x, y1: y, x2: b.x + BOX_W + 2, y2: y };
}

const POINTS = PIPELINE_STAGES.map((_, i) => place(i));
const EDGES = POINTS.slice(1).map((point, i) => edge(POINTS[i], point));

/**
 * The scan pipeline of guide chapter 3, placed by a `<!-- figure:pipeline -->`
 * line. Links are plain hrefs: the guide page's click handler routes them.
 */
@Component({
  selector: 'sb-guide-pipeline-diagram',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[style.--pl-scale]': 'scale()' },
  template: `
    @if (phone()) {
      <ol class="pipeline-steps" aria-label="The scan pipeline">
        @for (stage of stages(); track stage.label) {
          <li><a class="pipeline-node" [class.pipeline-link]="!!stage.href" [class.sb-hit]="!!stage.href"
                 [attr.href]="stage.href">{{ stage.label }}</a></li>
        }
      </ol>
    } @else {
      <svg viewBox="0 0 680 272" role="group" aria-label="The scan pipeline, from the watchlist to a closed trade">
        <defs>
          <marker id="guide-pipeline-arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7"
                  orient="auto-start-reverse">
            <path d="M0,0 L8,4 L0,8 Z" class="arrowhead" />
          </marker>
        </defs>
        @for (e of edges; track $index) {
          <line class="edge" [attr.x1]="e.x1" [attr.y1]="e.y1" [attr.x2]="e.x2" [attr.y2]="e.y2"
                marker-end="url(#guide-pipeline-arrow)" />
        }
        @for (stage of stages(); track stage.label) {
          <a class="pipeline-node" [class.pipeline-link]="!!stage.href" [attr.href]="stage.href"
             [attr.aria-label]="stage.href ? stage.label : null">
            <rect [attr.x]="stage.x" [attr.y]="stage.y" width="140" height="52" rx="8" />
            @for (line of stage.text; track $index) {
              <text [attr.x]="stage.x + 70" [attr.y]="line.y">{{ line.text }}</text>
            }
          </a>
        }
      </svg>
    }
  `,
  styles: `
    :host { display: block; max-width: 680px; margin: var(--space-14) 0; }
    svg { display: block; width: 100%; height: auto; overflow: visible; }
    .edge { fill: none; stroke: var(--text-faint); stroke-width: 1.5; }
    .arrowhead { fill: var(--text-faint); }
    rect { fill: var(--surface); stroke: var(--border); stroke-width: 1; }
    text {
      fill: var(--text); font-weight: 600; text-anchor: middle; dominant-baseline: middle;
      font-size: calc(var(--text-chip) / var(--pl-scale, 1));
    }
    .pipeline-link rect { stroke: var(--accent); }
    .pipeline-link text { fill: var(--accent); }
    .pipeline-link:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

    .pipeline-steps {
      display: flex; flex-direction: column; gap: var(--space-6); margin: 0; padding-left: var(--space-20);
      font-size: var(--text-body); overflow-wrap: anywhere;
    }
    .pipeline-steps li { padding: var(--space-4) 0; }
    .pipeline-node { color: var(--text); text-decoration: none; }
    .pipeline-steps .pipeline-link { color: var(--accent); text-decoration: underline; }
  `,
})
export class GuidePipelineDiagram {
  private readonly store = inject(GuideStore);
  protected readonly phone = inject(ViewportService).isPhone;
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly width = chartWidth(() => this.host.nativeElement, VIEWBOX_W);
  /** 1 at full size, below 1 as the host narrows; the CSS divides the text token by it. */
  protected readonly scale = computed(() => Math.round(Math.min(1, this.width() / VIEWBOX_W) * 1000) / 1000);
  protected readonly edges = EDGES;

  protected readonly stages = computed(() => {
    const written = new Set(this.store.chapters().map((c) => c.slug));
    return PIPELINE_STAGES.map((stage, i) => {
      const { x, y } = POINTS[i];
      const middle = y + BOX_H / 2 - ((stage.lines.length - 1) * LINE_GAP) / 2;
      return {
        ...stage, x, y,
        href: written.has(stage.slug) ? `/insights/guide/${stage.slug}` : null,
        text: stage.lines.map((line, j) => ({ text: line, y: middle + j * LINE_GAP })),
      };
    });
  });
}
