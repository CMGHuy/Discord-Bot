import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
} from '@angular/core';
import { Router } from '@angular/router';

import { SearchIndexStore } from '../../stores/search-index.store';
import { Button } from '../../ui/button';
import { DensityService } from '../../ui/density.service';
import { FocusTrap } from '../../ui/focus-trap';
import { Icon } from '../../ui/icon';
import {
  PALETTE_GROUP_LABELS,
  PREFERENCE_ITEMS,
  PaletteItem,
  emptyQueryItems,
  pageItems,
  rankPaletteItems,
  tickerItems,
  tradeItems,
} from './palette-items';

/** The longest list rendered for a typed query; the ranking puts the best first. */
export const PALETTE_MAX_RESULTS = 50;

/** Input types that take no typing, so `/` there may open the palette. */
const NON_TEXT_INPUT_TYPES = new Set([
  'button', 'checkbox', 'color', 'file', 'hidden', 'image', 'radio', 'range', 'reset', 'submit',
]);

/** True when a keystroke on `el` is someone typing: `/` must reach it. */
export function isTypingTarget(el: Element | null): boolean {
  if (!el) return false;
  if (el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement) return true;
  if (el instanceof HTMLInputElement) return !NON_TEXT_INPUT_TYPES.has(el.type);
  return el.closest('[contenteditable]:not([contenteditable="false"])') !== null;
}

/** Ctrl+K or ⌘K anywhere; a bare `/` only outside a text field (spec §3.1). */
export function isPaletteShortcut(event: KeyboardEvent): boolean {
  if (event.altKey) return false;
  if (event.key === 'k' || event.key === 'K') return event.ctrlKey || event.metaKey;
  if (event.key !== '/' || event.ctrlKey || event.metaKey) return false;
  return !isTypingTarget(event.target instanceof Element ? event.target : null);
}

/** The trigger's hint: `⌘K` on Apple platforms, `Ctrl K` everywhere else. */
export function shortcutLabel(platform: string): string {
  return /mac|iphone|ipad/i.test(platform) ? '⌘K' : 'Ctrl K';
}

const STEPS = new Map<string, number>([['ArrowDown', 1], ['ArrowUp', -1]]);

const optionId = (index: number): string => `palette-option-${index}`;

/**
 * The command palette -- v195 §3.1: jump to a ticker, a trade or plan, a
 * page or a workspace tab, or set the row density.
 *
 * Navigation and preferences only. It injects the router, the search index
 * and the density service and nothing else, and its items are plain data
 * (palette-items.ts), so no path through it can act on the book or the bot.
 * command-palette.spec.ts pins the injections.
 *
 * A modal: scrim plus a centred panel (a full-screen sheet below 640px),
 * focus trapped and returned to whatever opened it (FocusTrap). The field is
 * an ARIA combobox over a listbox: the arrows move the active option, Enter
 * or a click opens it, Escape and the scrim close. The options take
 * `tabindex="-1"`, so Tab cycles the field and Close only.
 *
 * The shell owns the open state; this asks to close (`closed`). Opening
 * starts fresh (empty query, first row active) and asks the index for its
 * rows, which it reads once and caches (SearchIndexStore).
 */
@Component({
  selector: 'sb-command-palette',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, FocusTrap, Icon],
  host: { '(document:keydown.escape)': 'onEscape()' },
  template: `
    @if (open()) {
      <div class="scrim" aria-hidden="true" (click)="closed.emit()"></div>
      <div class="dialog elev-overlay" role="dialog" aria-modal="true" aria-label="Search or jump" sbFocusTrap>
        <div class="field">
          <span class="glyph" aria-hidden="true"><sb-icon name="search" /></span>
          <input
            class="query"
            type="text"
            role="combobox"
            autocomplete="off"
            spellcheck="false"
            aria-label="Search tickers, trades, pages and preferences"
            aria-autocomplete="list"
            aria-expanded="true"
            aria-controls="palette-results"
            [attr.aria-activedescendant]="activeId()"
            placeholder="Search or jump…"
            [value]="query()"
            (input)="onInput($any($event.target).value)"
            (keydown)="onKeydown($event)"
          />
          <button sb-button variant="ghost" type="button" class="close" (click)="closed.emit()">Close</button>
        </div>
        @if (index.failed()) {
          <p class="unavailable" role="status">Tickers unavailable: pages and preferences still work.</p>
        }
        <ul id="palette-results" class="results" role="listbox" aria-label="Results">
          @for (item of results(); track item.key; let i = $index) {
            <li
              class="option"
              role="option"
              tabindex="-1"
              [id]="optionId(i)"
              [class.active]="i === active()"
              [attr.aria-selected]="i === active()"
              (mousemove)="active.set(i)"
              (click)="choose(item)"
              (keydown.enter)="choose(item)"
            >
              <span class="label">{{ item.label }}</span>
              @if (item.sub) {
                <span class="sub">{{ item.sub }}</span>
              }
              <span class="kind">{{ kindOf(item) }}</span>
            </li>
          }
        </ul>
        @if (results().length === 0) {
          <p class="none" role="status">No matches for “{{ query().trim() }}”</p>
        }
      </div>
    }
  `,
  styles: `
    :host { display: contents; }
    .scrim { position: fixed; inset: 0; z-index: 40; background: var(--scrim-soft); }
    .dialog {
      position: fixed;
      z-index: 41;
      top: 12vh;
      left: 50%;
      transform: translateX(-50%);
      width: min(640px, calc(100vw - 2 * var(--space-20)));
      max-height: 70vh;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .field {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      padding: var(--space-6) var(--space-10);
      border-bottom: 1px solid var(--border);
    }
    .field:focus-within { border-bottom-color: var(--accent); }
    .glyph { display: inline-flex; line-height: 0; color: var(--text-muted); }
    .query {
      flex: 1 1 auto;
      min-width: 0;
      min-height: var(--control-h);
      border: 0;
      background: none;
      color: var(--text);
      font: inherit;
      font-size: var(--text-control);
    }
    .query::placeholder { color: var(--text-muted); }
    /* The field's own ring would sit inside the panel edge; the accent rule
       under the field row (.field:focus-within) is the focus cue. */
    .query:focus-visible { outline: none; }
    .results { flex: 1 1 auto; margin: 0; padding: var(--space-4); overflow-y: auto; list-style: none; }
    .option {
      display: flex;
      align-items: center;
      gap: var(--space-8);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      border-radius: var(--control-radius);
      color: var(--text-secondary);
      cursor: pointer;
      transition: background var(--transition), color var(--transition);
    }
    .option.active { background: var(--surface-raised); color: var(--text); }
    .label, .sub { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .label { flex: 0 1 auto; font-size: var(--text-body); }
    .sub { flex: 1 1 auto; color: var(--text-muted); font-size: var(--text-table); }
    .kind { flex: none; margin-left: auto; color: var(--text-muted); font-size: var(--text-micro); }
    .unavailable, .none { margin: 0; padding: var(--space-8) var(--space-14); color: var(--text-muted); font-size: var(--text-table); }
    @media (max-width: 639px) {
      .dialog {
        inset: 0;
        transform: none;
        width: auto;
        max-height: none;
        border-radius: 0;
        padding-bottom: env(safe-area-inset-bottom);
      }
    }
  `,
})
export class CommandPalette {
  readonly open = input(false);
  readonly closed = output<void>();

  protected readonly index = inject(SearchIndexStore);
  private readonly density = inject(DensityService);
  private readonly router = inject(Router);

  protected readonly query = signal('');
  protected readonly active = signal(0);
  protected readonly optionId = optionId;

  private readonly pages = pageItems();

  private readonly items = computed<PaletteItem[]>(() => [
    ...tickerItems(this.index.tickers()),
    ...tradeItems(this.index.trades()),
    ...this.pages,
    ...PREFERENCE_ITEMS,
  ]);

  protected readonly results = computed<PaletteItem[]>(() =>
    this.query().trim()
      ? rankPaletteItems(this.query(), this.items()).slice(0, PALETTE_MAX_RESULTS)
      : emptyQueryItems(this.items()),
  );

  protected readonly activeId = computed(() => (this.results().length > 0 ? optionId(this.active()) : null));

  constructor() {
    // Each open starts fresh and asks the index (a no-op while its cache is
    // fresh). Untracked: only `open` drives this.
    effect(() => {
      if (!this.open()) return;
      untracked(() => {
        this.query.set('');
        this.active.set(0);
        this.index.ensure();
      });
    });
  }

  protected kindOf(item: PaletteItem): string {
    return PALETTE_GROUP_LABELS[item.group];
  }

  protected onInput(value: string): void {
    this.query.set(value);
    this.active.set(0);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const step = STEPS.get(event.key);
    if (step !== undefined) {
      event.preventDefault();
      this.move(step);
      return;
    }
    if (event.key !== 'Enter') return;
    event.preventDefault();
    const item = this.results()[this.active()];
    if (item) this.choose(item);
  }

  protected choose(item: PaletteItem): void {
    if (item.density) this.density.set(item.density);
    else if (item.route) void this.router.navigate([item.route], { queryParams: item.queryParams ?? {} });
    this.closed.emit();
  }

  protected onEscape(): void {
    if (this.open()) this.closed.emit();
  }

  private move(step: number): void {
    const count = this.results().length;
    if (count === 0) return;
    const next = (this.active() + step + count) % count;
    this.active.set(next);
    // jsdom has no scrollIntoView; a browser keeps the active row in view.
    document.getElementById(optionId(next))?.scrollIntoView?.({ block: 'nearest' });
  }
}
