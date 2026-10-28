import { Injectable, Signal, inject, signal } from '@angular/core';
import { Title } from '@angular/platform-browser';
import {
  ActivatedRouteSnapshot,
  RouterStateSnapshot,
  TitleStrategy,
} from '@angular/router';

/**
 * The active route's title and subtitle, as signals — v85 D4.
 *
 * The shell's top bar renders these; workspaces no longer render a heading of
 * their own. One page, one title, and it lives where the design puts it.
 *
 * v195 Phase 3: plus the breadcrumb's detail segment ('NVDA #812', a long
 * date), which only a detail route knows. It sets it once its data is loaded
 * -- from an effect, never its constructor: the router updates the title
 * after it activates the route, and every title update that moves to another
 * path clears the detail, so a page never shows the last record's name. A
 * query-only navigation (a tab switch) stays on the path and keeps it.
 */
@Injectable({ providedIn: 'root' })
export class RouteTitleService {
  private readonly _title = signal('');
  private readonly _subtitle = signal<string | null>(null);
  private readonly _detail = signal<string | null>(null);
  /** The path the current title belongs to; null after a path-less set(). */
  private path: string | null = null;

  readonly title: Signal<string> = this._title.asReadonly();
  readonly subtitle: Signal<string | null> = this._subtitle.asReadonly();
  readonly detail: Signal<string | null> = this._detail.asReadonly();

  set(title: string, subtitle: string | null, path: string | null = null): void {
    this._title.set(title);
    this._subtitle.set(subtitle);
    if (path === null || path !== this.path) this._detail.set(null);
    this.path = path;
  }

  /** The breadcrumb detail segment; '' is stored as none. */
  setDetail(detail: string | null): void {
    this._detail.set(detail || null);
  }
}

/** Reads `title` the way Angular already does, and `data.subtitle` from the
 *  deepest activated route that defines one. Still sets `document.title`:
 *  this replaces the default strategy rather than sitting beside it. */
@Injectable({ providedIn: 'root' })
export class SubtitleTitleStrategy extends TitleStrategy {
  private readonly document = inject(Title);
  private readonly titles = inject(RouteTitleService);

  override updateTitle(snapshot: RouterStateSnapshot): void {
    const title = this.buildTitle(snapshot) ?? '';
    this.titles.set(title, subtitleOf(snapshot.root), pathOf(snapshot.url));
    if (title) this.document.setTitle(title);
  }
}

/** The deepest defined subtitle, or null. Walks the whole firstChild chain
 *  rather than reading the root: with `loadChildren`, the route carrying the
 *  data may be either the parent entry or the lazy child. */
function subtitleOf(route: ActivatedRouteSnapshot): string | null {
  let found: string | null = null;
  for (let node: ActivatedRouteSnapshot | null = route; node; node = node.firstChild) {
    const value = node.data['subtitle'];
    if (typeof value === 'string') found = value;
  }
  return found;
}

/** The URL without its query or fragment: '/trades/812?tab=plan' ->
 *  '/trades/812'. Two navigations with the same path are the same page. */
function pathOf(url: string): string {
  return url.split(/[?#]/)[0];
}
