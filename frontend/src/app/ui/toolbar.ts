import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  signal,
  viewChild,
} from '@angular/core';

import { Viewport, ViewportService } from './breakpoints';
import { isInline } from './priority';

/**
 * A control bar that collapses rather than stacks — v95 §4.2.
 *
 * The problem this exists for: Trades at 390px put eight filter selects, a
 * date range, a column picker and two destructive buttons in a vertical
 * column ~1700px tall, so the first trade row was four screens down. Stacking
 * is what a flex-wrap bar does when it runs out of width, and it is the wrong
 * answer for a bar with more than about four controls.
 *
 * Controls are projected by `[slot]` and REPARENTED — the same element is
 * moved between the inline row and the sheet, never destroyed and rebuilt. A
 * control that was recreated would lose its focus, its open dropdown and any
 * uncommitted text the moment the viewport crossed a breakpoint mid-edit.
 *
 * That is also why the projection is manual rather than a pair of
 * `<ng-content select>` outlets: `select` is a static attribute and each
 * outlet projects once, so a set of control ids only known at runtime cannot
 * be expressed with it. Content lands in one hidden holder and an effect
 * appends each element to the container its floor puts it in.
 *
 * The consequence for call sites: every projected control must be a single
 * element carrying `slot="<id>"`, and must not sit inside a host-side `@if`
 * or `@for` — Angular would reinsert it at its declared position, undoing the
 * move.
 */
export interface ToolbarControl {
  /** Matches the projected element's `slot` attribute. */
  id: string;
  /** Used in the sheet's heading and for the accessible name. */
  label: string;
  inlineFrom?: Viewport;
  /** Non-default — feeds the badge. See v95 §5 guard 1. */
  active?: boolean;
}

@Component({
  selector: 'sb-toolbar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="toolbar-inline" #inlineHost></div>

    @if (demoted().length) {
      <button
        type="button"
        class="toolbar-sheet-button"
        [attr.aria-expanded]="open()"
        [attr.aria-label]="sheetLabel()"
        (click)="open.set(!open())"
      >
        Filters
        <span class="count num">{{ demoted().length }}</span>
        @if (activeCount()) { <span class="active-dot" [attr.data-count]="activeCount()"></span> }
      </button>
    }

    <div class="toolbar-sheet" [class.open]="open()" #sheetHost></div>

    <div class="toolbar-source" hidden #sourceHost><ng-content /></div>
  `,
  styles: `
    :host { display: flex; align-items: center; gap: var(--space-10); flex-wrap: wrap; container: toolbar / inline-size; }
    .toolbar-inline { display: flex; align-items: center; gap: var(--space-10); flex-wrap: wrap; min-width: 0; max-width: 100%; }
    /* v179 §3.3: the same button as sb-column-picker's .trigger -- one
       height, one surface, the count as a badge. Without these rules the
       browser's default grey button showed through ("Filters 13"). */
    .toolbar-sheet-button {
      display: inline-flex;
      align-items: center;
      gap: var(--space-6);
      min-height: var(--control-h);
      padding: 0 var(--space-10);
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--control-radius);
      color: var(--text);
      font: inherit;
      font-size: var(--text-table);
      cursor: pointer;
      transition: border-color var(--transition);
    }
    .toolbar-sheet-button:hover { border-color: var(--border-strong); }
    .toolbar-sheet-button:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    .count {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 1.5em;
      padding: 0 var(--space-4);
      border-radius: var(--chip-radius);
      background: var(--accent-soft);
      color: var(--text);
      font-size: var(--text-chip);
    }
    /* Selects in the sheet share one width rule: equal columns, two on a
       phone-width bar (the rule sb-filter-bar's container query already uses). */
    .toolbar-sheet { display: none; width: 100%; gap: var(--space-10); }
    .toolbar-sheet.open { display: grid; grid-template-columns: repeat(auto-fill, minmax(12rem, 1fr)); align-items: end; }
    @container toolbar (max-width: 639px) {
      .toolbar-sheet.open { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    }
    /* Share the phone flex row with the projected controls: a boxed inline
       wrapper keeps Filters below Columns after chips fill their own line. */
    @media (max-width: 639px) {
      .toolbar-inline { display: contents; }
    }
    .active-dot::after { content: attr(data-count); color: var(--accent); }
  `,
})
export class Toolbar {
  private readonly viewportService = inject(ViewportService);

  readonly controls = input<ToolbarControl[]>([]);
  /** Test override — jsdom resolves no media query. */
  readonly viewportAt = input<Viewport | null>(null);

  protected readonly open = signal(false);

  private readonly inlineHost = viewChild.required<ElementRef<HTMLElement>>('inlineHost');
  private readonly sheetHost = viewChild.required<ElementRef<HTMLElement>>('sheetHost');
  private readonly sourceHost = viewChild.required<ElementRef<HTMLElement>>('sourceHost');

  private readonly viewport = computed<Viewport>(
    () => this.viewportAt() ?? this.viewportService.viewport(),
  );

  protected readonly inlineControls = computed(() =>
    this.controls().filter((c) => isInline(c.inlineFrom, this.viewport())),
  );

  protected readonly demoted = computed(() => {
    const inline = new Set(this.inlineControls().map((c) => c.id));
    return this.controls().filter((c) => !inline.has(c.id));
  });

  /** Guard 1 (v95 §5): a filter you cannot see that is narrowing your data is
   *  a correctness bug, so the count of ACTIVE demoted controls is surfaced
   *  separately from the count of demoted ones. */
  protected readonly activeCount = computed(
    () => this.demoted().filter((c) => c.active).length,
  );

  protected readonly sheetLabel = computed(() => {
    const active = this.activeCount();
    const total = this.demoted().length;
    return active
      ? `Filters — ${total} hidden, ${active} active`
      : `Filters — ${total} hidden`;
  });

  constructor() {
    effect(() => {
      const inlineIds = new Set(this.inlineControls().map((c) => c.id));
      const inlineHost = this.inlineHost().nativeElement;
      const sheetHost = this.sheetHost().nativeElement;

      for (const element of this.slotted()) {
        const id = element.getAttribute('slot');
        const target = id !== null && inlineIds.has(id) ? inlineHost : sheetHost;
        // appendChild on a node already in `target` would still reorder it,
        // so the parent check is not an optimisation -- it keeps a control
        // that did not move from jumping to the end of its row.
        if (element.parentElement !== target) target.appendChild(element);
      }
    });
  }

  /** Every projected control, wherever it currently sits. */
  private slotted(): HTMLElement[] {
    return [this.sourceHost(), this.inlineHost(), this.sheetHost()]
      .flatMap((host) => [...host.nativeElement.children])
      .filter((node): node is HTMLElement => node instanceof HTMLElement && node.hasAttribute('slot'));
  }
}
