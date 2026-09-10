import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterNextRender,
  effect,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';

import { FocusTrap } from './focus-trap';

/* Spec 3's layout inventory: panel, tab bar, split view, drawer. */

/**
 * A titled box. The default container for anything that is not a full
 * workspace — an Analytics section, the Risk exposure table, a detail tab.
 *
 * The `actions` slot exists so a panel's controls sit on its own header rather
 * than floating above it; a filter that belongs to one table should be
 * unambiguously attached to that table.
 */
@Component({
  selector: 'sb-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="panel">
      @if (heading(); as text) {
        <header>
          <h2 class="sb-label">{{ text }}</h2>
          <div class="actions"><ng-content select="[panel-actions]" /></div>
        </header>
      }
      <div class="body" [class.flush]="flush()">
        <ng-content />
      </div>
    </section>
  `,
  styles: `
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
    }
    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: var(--space-10);
      padding: var(--space-10) var(--space-14);
      border-bottom: 1px solid var(--border);
    }
    /* Typography is the global .sb-label (v80 D3); only the UA margin is
       this component's business. */
    h2 { margin: 0; }
    .actions { display: flex; align-items: center; gap: var(--space-8); }
    .body { padding: var(--space-14); }
    /* Tables draw their own edge-to-edge padding. */
    .flush { padding: 0; }
  `,
})
export class Panel {
  readonly heading = input<string | null>(null);
  readonly flush = input(false);
}

export interface Tab {
  id: string;
  label: string;
}

/**
 * The tab strip over Trade detail's five tabs and Analytics' four.
 *
 * Tabs here are sections of one entity, which is the only thing they are
 * allowed to be: Trades deliberately uses a filter chip row for status instead,
 * because tabs over statuses would reintroduce the "separate page per state"
 * model the whole IA change exists to abolish.
 *
 * Arrow keys move between tabs, which is what the tab pattern requires and
 * what a row of plain buttons does not give you.
 */
@Component({
  selector: 'sb-tab-bar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '(window:resize)': 'measure()' },
  template: `
    <div class="strip" [class.fade-start]="fadeStart()" [class.fade-end]="fadeEnd()">
      <div #tabList class="tabs" role="tablist" (keydown)="onKeydown($event)" (scroll)="measure()">
        @for (tab of tabs(); track tab.id) {
        <button
          type="button"
          role="tab"
          class="tab"
          [class.active]="tab.id === active()"
          [attr.aria-selected]="tab.id === active()"
          [tabindex]="tab.id === active() ? 0 : -1"
          (click)="activeChange.emit(tab.id)"
        >
          {{ tab.label }}
        </button>
        }
      </div>
    </div>
  `,
  styles: `
    :host { display: block; }
    .strip { position: relative; border-bottom: 1px solid var(--border); }
    .tabs { display: flex; gap: var(--space-4); overflow-x: auto; scrollbar-width: none; }
    .tabs::-webkit-scrollbar { display: none; }
    .tab {
      flex: 0 0 auto;
      min-height: var(--control-h);
      padding: var(--space-8) var(--space-14);
      background: none;
      border: 0;
      border-bottom: 2px solid transparent;
      color: var(--text-secondary);
      font: inherit;
      font-size: var(--text-table);
      font-weight: 600;
      white-space: nowrap;
      cursor: pointer;
      transition: color var(--transition), border-color var(--transition);
    }
    .tab:hover { color: var(--text); }
    .tab:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .active { color: var(--text); border-bottom-color: var(--accent); }
    .strip::before, .strip::after {
      content: ''; position: absolute; top: 0; bottom: 0; width: var(--space-20);
      pointer-events: none; opacity: 0; transition: opacity var(--transition);
    }
    .strip::before { left: 0; background: linear-gradient(to right, var(--bg), transparent); }
    .strip::after { right: 0; background: linear-gradient(to left, var(--bg), transparent); }
    .fade-start::before, .fade-end::after { opacity: 1; }
  `,
})
export class TabBar {
  readonly tabs = input.required<Tab[]>();
  readonly active = input.required<string>();
  readonly activeChange = output<string>();
  private readonly tabList = viewChild.required<ElementRef<HTMLElement>>('tabList');
  protected readonly fadeStart = signal(false);
  protected readonly fadeEnd = signal(false);

  constructor() { afterNextRender(() => this.measure()); }

  protected measure(): void {
    const el = this.tabList().nativeElement;
    const overflow = el.scrollWidth - el.clientWidth;
    this.fadeStart.set(overflow > 1 && el.scrollLeft > 1);
    this.fadeEnd.set(overflow > 1 && el.scrollLeft < overflow - 1);
  }

  protected onKeydown(event: KeyboardEvent): void {
    const delta = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (delta === 0) return;
    event.preventDefault();

    const tabs = this.tabs();
    const current = tabs.findIndex((tab) => tab.id === this.active());
    // Wraps, per the tab pattern: the end of the strip is not a dead end.
    const next = tabs[(current + delta + tabs.length) % tabs.length];
    if (next) this.activeChange.emit(next.id);
  }
}


/**
 * The one sanctioned control row.
 *
 * Before this, 47 rows across the workspaces each picked their own
 * `align-items` — `center`, `baseline`, `flex-start`, `stretch` — and a row
 * mixing a labelled input with a bare button could not align under any of
 * them, because the two controls disagreed about where their label went and
 * differed by 4px in height. `--control-h` and the checkbox's top label fixed
 * the controls; this fixes the container.
 *
 * **`flex-end`, and the reason matters.** A labelled control is label-band +
 * control-band; a bare button is control-band only. Aligning on the BOTTOM
 * edge is the only rule under which both land on the same line, whatever the
 * label does above it.
 *
 * Flexbox already aligns per-line when wrapping — `align-items` applies within
 * each flex line, not across the container — so a wrapped second line aligns
 * with itself for free. That was never the bug; mismatched control heights
 * inside one line was.
 *
 * Every row collapses to a full-width column below `sm` (640px); v80 D4 made
 * that automatic. `stacked` still sets its class and does nothing else.
 */
@Component({
  selector: 'sb-control-row',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="row" [class.stacked]="stacked()"><ng-content /></div>`,
  styles: `
    /* Block, not the inline default. Consumers put margin, padding, a
       background and position:sticky on this element (the settings save bar
       does all four) -- every one of those is ignored or half-applied on an
       inline box, and silently, which is the worst way to lose a layout. */
    :host { display: block; }
    .row {
      display: flex;
      align-items: flex-end;
      align-content: flex-start;
      flex-wrap: wrap;
      gap: var(--space-10);
    }
    /* 640 is breakpoints.ts's sm floor, repeated as a literal because
       @media cannot evaluate var() -- the same reason the breakpoints are
       not tokens. breakpoints.spec.ts pins the arithmetic. */
    @media (max-width: 639px) {
      .row { flex-direction: column; align-items: stretch; }
    }
  `,
})
export class ControlRow {
  readonly stacked = input(false);
}


/**
 * A panel that slides in from the right — row detail that is too big to
 * expand inline, without navigating away from the list behind it.
 *
 * `<dialog>` again, for the same reasons as `ConfirmDialog`: the browser owns
 * the top layer, Escape, focus trapping and making the background inert.
 */
@Component({
  selector: 'sb-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FocusTrap],
  template: `
    <dialog #dialog class="drawer elev-overlay" (close)="closed.emit()" (cancel)="closed.emit()">
      <!-- Only present while open, so sbFocusTrap's constructor/ngOnDestroy
           pair runs on exactly open and close -- see focus-trap.ts. -->
      @if (open()) {
        <div sbFocusTrap class="drawer-content">
          <header>
            <h2>{{ heading() }}</h2>
            <button type="button" class="close" aria-label="Close" (click)="dismiss()">×</button>
          </header>
          <div class="body"><ng-content /></div>
        </div>
      }
    </dialog>
  `,
  styles: `
    /* Structural only -- exists so sbFocusTrap has one element to own, not
       a layout box. Everything inside lays out exactly as if it were still
       a direct child of dialog. */
    .drawer-content { display: contents; }

    .drawer {
      width: min(480px, 100vw);
      max-width: none;
      height: 100dvh;
      max-height: 100dvh;
      margin: 0 0 0 auto;
      padding: 0;
      color: var(--text);
    }
    .drawer::backdrop { background: var(--scrim); }
    /* elev-overlay's border-radius and 4-sided border assume a panel that
     * floats clear of the viewport on every edge. This one doesn't -- right,
     * top and bottom sit flush against the screen, so rounding those corners
     * would curve them away from the actual corners and show the scrim
     * through the gap. Only the left edge is a real boundary against the
     * page behind it, so that is the only side that keeps a border. */
    .drawer.elev-overlay {
      border-radius: 0;
      border-width: 0 0 0 1px;
    }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: var(--space-14);
      border-bottom: 1px solid var(--border);
    }
    h2 { font-size: var(--text-subhead); font-weight: 600; }
    .close {
      min-width: var(--control-h);
      min-height: var(--control-h);
      padding: 0 var(--space-6);
      background: none;
      border: 0;
      color: var(--text-muted);
      font-size: var(--text-title);
      line-height: 1;
      cursor: pointer;
    }
    .close:hover { color: var(--text); }
    .body { padding: var(--space-14); overflow-y: auto; }
    @media (max-width: 639px) {
      .drawer { width: 100vw; }
    }
  `,
})
export class Drawer {
  readonly open = input(false);
  readonly heading = input('');
  readonly closed = output<void>();

  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  constructor() {
    effect(() => {
      const element = this.dialog().nativeElement;
      if (this.open() && !element.open) element.showModal();
      else if (!this.open() && element.open) element.close();
    });
  }

  protected dismiss(): void {
    // Through the dialog's own close event, so the button and Escape are one
    // path rather than two that can drift.
    this.dialog().nativeElement.close();
  }
}
