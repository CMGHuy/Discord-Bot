import { DestroyRef, Directive, ElementRef, effect, inject, input, untracked } from '@angular/core';

import { MotionStarts } from './motion-starts';
import { MotionService } from './motion.service';
import { RouteEntryService } from './route-entry.service';

export type DrawShape = 'inset' | 'circle';

/** `--dur-draw` (1200ms) plus margin: the class never outlives a lost animationend by much. */
export const DRAW_FALLBACK_MS = 1400;

const CLASS_FOR: Record<DrawShape, string> = { inset: 'sb-draw-in', circle: 'sb-draw-in-radial' };

/**
 * Chart draw-in (spec v168 §3 #9): a `clip-path` reveal on the chart's host,
 * the same for SVG and canvas. Not a stroke-dash animation: jsdom has no
 * `getTotalLength()`, and the sparkline's non-scaling stroke measures dashes
 * in screen space but lengths in viewBox units.
 *
 * Spends `RouteEntryService.claim(key)` once per instance, after first render
 * and only once `drawReady` is true, whatever the mode; clips only when the
 * claim was fresh and Motion is On. A data update repaints without redrawing,
 * and a chart that `sb-async` re-creates after a refetch finds its claim
 * spent, so it shows at once.
 */
@Directive({ selector: '[sbDrawIn]' })
export class DrawIn {
  /** Stable per chart: `sparkline:<label>`, `gauge:<label>`, `donut`, `dot-plot:<yLabel>`, `chart:<caption>`. */
  readonly sbDrawIn = input.required<string>();
  readonly drawShape = input<DrawShape>('inset');
  /** False while the host shows a placeholder (chart-container loading): the claim waits. */
  readonly drawReady = input(true);

  private readonly host: Element = inject<ElementRef<Element>>(ElementRef).nativeElement;
  private readonly entry = inject(RouteEntryService);
  private readonly motion = inject(MotionService);
  private readonly starts = inject(MotionStarts);
  private spent = false;
  private playing: string | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;

  private readonly onEnd = (event: Event): void => {
    if (event.target === this.host) this.finish();
  };

  constructor() {
    effect(() => {
      if (!this.drawReady() || this.spent) return;
      untracked(() => this.begin());
    });
    inject(DestroyRef).onDestroy(() => this.finish());
  }

  /** The claim is always spent first; the mode only decides whether to clip. */
  private begin(): void {
    this.spent = true;
    const key = this.sbDrawIn();
    if (!this.entry.claim(key) || !this.motion.full()) return;
    this.start(CLASS_FOR[this.drawShape()], key);
  }

  private start(cls: string, key: string): void {
    this.playing = cls;
    this.host.classList.add(cls);
    this.host.addEventListener('animationend', this.onEnd);
    this.starts.record('draw-in', key);
    this.timer = setTimeout(() => this.finish(), DRAW_FALLBACK_MS);
  }

  private finish(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.host.removeEventListener('animationend', this.onEnd);
    if (this.playing !== null) this.host.classList.remove(this.playing);
    this.playing = null;
  }
}
