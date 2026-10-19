import { DestroyRef, Directive, ElementRef, effect, inject, untracked } from '@angular/core';

import { MotionStarts } from './motion-starts';
import { MotionService } from './motion.service';
import { RouteEntryService } from './route-entry.service';

/**
 * How long the route host keeps `.sb-entering`: the longest stagger delay
 * (8 children x 60ms) plus `--dur-enter` (420ms) is 900ms, rounded up.
 */
export const ENTRANCE_FALLBACK_MS = 1000;

const ENTERING = 'sb-entering';

/**
 * The route host (spec v168 §3 #1 and #2, amendment 2).
 *
 * Sits on the shell's persistent `div.workspace-content`, so the class has to
 * be re-triggered on each activation: remove, reflow, add. The entrance and the
 * CSS stagger of the workspace's top-level layout children both hang off
 * `.sb-entering` in `styles/motion.css`; this directive only decides *when*.
 *
 * It animates via `animation`, not the host's existing `.route-pending`
 * opacity `transition`, which stays as it is.
 *
 * The class is removed by the timer only. The host's own `animationend`
 * arrives at 420ms while staggered children are still running; removing the
 * class then would snap them to their final state.
 */
@Directive({ selector: '[sbRouteEntrance]' })
export class RouteEntrance {
  private readonly host: HTMLElement = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly entry = inject(RouteEntryService);
  private readonly motion = inject(MotionService);
  private readonly starts = inject(MotionStarts);
  private seen = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    effect(() => {
      const id = this.entry.activation();
      untracked(() => this.onActivation(id));
    });
    inject(DestroyRef).onDestroy(() => this.finish());
  }

  /** The claim is always spent first; the mode only decides whether to play. */
  private onActivation(id: number): void {
    if (id === 0 || id === this.seen) return;
    this.seen = id;
    if (!this.entry.claim('route')) return;
    if (this.motion.active()) this.start();
  }

  private start(): void {
    this.finish();
    void this.host.offsetWidth;
    this.host.classList.add(ENTERING);
    this.starts.record('entrance', 'route');
    this.timer = setTimeout(() => this.finish(), ENTRANCE_FALLBACK_MS);
  }

  private finish(): void {
    if (this.timer !== null) clearTimeout(this.timer);
    this.timer = null;
    this.host.classList.remove(ENTERING);
  }
}
