import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  ElementRef,
  afterNextRender,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

/** Where the bar sits, in the sidebar's scrolled coordinate space. */
export interface IndicatorBox {
  top: number;
  height: number;
}

/**
 * The active link's box relative to `container` (the scrolling `.sidebar`):
 * rect difference, minus the container's top border, plus its scroll, so the
 * bar scrolls with the links. `null` when no link is active.
 */
export function indicatorBox(container: HTMLElement): IndicatorBox | null {
  const link = container.querySelector<HTMLElement>('.nav a.active');
  if (!link) return null;
  const outer = container.getBoundingClientRect();
  const inner = link.getBoundingClientRect();
  return { top: inner.top - outer.top - container.clientTop + container.scrollTop, height: inner.height };
}

/**
 * One sliding rail for the active nav entry (spec v168 §3 #6), replacing the
 * per-link left border. It lives in `.sidebar`, not in a `.nav` list, because
 * the nav is three lists with group labels between them; the shell places
 * the host (shell.css) and this component only moves the bar.
 *
 * It remeasures after first render, after every navigation, and whenever the
 * sidebar, a list or a link changes size: a sidebar collapse, a text-size
 * change (--text-scale) and a list growing all move the active link without
 * a navigation. The bar declares no transition here; styles/motion.css gives
 * it a spring under Motion = On and a fade under Reduced, and under Off it
 * jumps.
 */
@Component({
  selector: 'sb-nav-indicator',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span class="nav-indicator" aria-hidden="true" [class.hidden]="!box()"
    [style.transform]="'translateY(' + (box()?.top ?? 0) + 'px)'"
    [style.height.px]="box()?.height ?? 0"></span>`,
  styles: `
    .nav-indicator {
      position: absolute;
      top: 0;
      left: 0;
      width: 2px;
      background: var(--accent);
      pointer-events: none;
    }
    .nav-indicator.hidden { opacity: 0; }
  `,
})
export class NavIndicator {
  protected readonly box = signal<IndicatorBox | null>(null);

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private readonly destroyRef = inject(DestroyRef);
  private pending: ReturnType<typeof setTimeout> | undefined;

  constructor() {
    inject(Router).events.pipe(
      filter((event) => event instanceof NavigationEnd),
      takeUntilDestroyed(),
    ).subscribe(() => {
      // RouterLinkActive sets `active` in a microtask after NavigationEnd;
      // a macrotask runs after it.
      clearTimeout(this.pending);
      this.pending = setTimeout(() => this.measure(), 0);
    });
    this.destroyRef.onDestroy(() => clearTimeout(this.pending));
    afterNextRender(() => {
      this.measure();
      this.observe();
    });
  }

  private measure(): void {
    const container = this.host.parentElement;
    this.box.set(container ? indicatorBox(container) : null);
  }

  /** jsdom (and very old browsers) have no ResizeObserver: then only navigations remeasure. */
  private observe(): void {
    const container = this.host.parentElement;
    if (!container || typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => this.measure());
    observer.observe(container);
    container.querySelectorAll('.nav').forEach((list) => observer.observe(list));
    container.querySelectorAll('.nav a').forEach((link) => observer.observe(link));
    this.destroyRef.onDestroy(() => observer.disconnect());
  }
}
