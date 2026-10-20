import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  afterNextRender,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  untracked,
  viewChild,
} from '@angular/core';

import { Viewport, ViewportService } from './breakpoints';
import { FocusTrap } from './focus-trap';
import { Icon, IconName } from './icon';
import { playExit } from './motion/exit';
import { MotionService } from './motion/motion.service';
import { isInline } from './priority';

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
    <section class="panel sb-panel sb-lift">
      @if (heading(); as text) {
        <header>
          <h2 class="sb-label">{{ text }}</h2>
          <div class="actions">
            <ng-content select="[panel-actions]" />
            @if (collapsible()) {
              <button
                type="button"
                class="panel-toggle"
                [attr.aria-expanded]="expanded()"
                [attr.aria-label]="(expanded() ? 'Collapse ' : 'Expand ') + text"
                (click)="expanded.set(!expanded())"
              >{{ expanded() ? '▾' : '▸' }}</button>
            }
          </div>
        </header>
      }
      @if (collapsed()) {
        <p class="panel-digest">{{ digest() }}</p>
      } @else {
        @if (problem(); as reason) {
          <p class="panel-problem" role="status">{{ reason }}</p>
        }
        <div class="body" [class.flush]="flush()">
          <ng-content />
        </div>
      }
    </section>
  `,
  styles: `
    .panel {
      background: var(--panel-bg);
      border: var(--panel-border);
      border-radius: var(--panel-radius);
      overflow: hidden;
    }
    /* v179 §3.3/§3.4 -- one header height and one baseline on every panel.
       At least one control tall (plus padding and the 1px rule, border-box),
       so a header holding only its label and one holding a button or a
       segmented control are the same height. The label, an N= count, an
       action and the hint glyph sit on the text BASELINE -- centring put an
       11px label 2-3px off a 14px button's text. align-content centres that
       one line inside the minimum height; it needs flex-wrap to act, and
       wrapping also lets the actions drop below the label on a narrow panel
       rather than squeeze it. */
    header {
      display: flex;
      flex-wrap: wrap;
      align-items: baseline;
      align-content: center;
      justify-content: space-between;
      gap: var(--space-6) var(--space-10);
      min-height: calc(var(--control-h) + 2 * var(--space-10) + 1px);
      padding: var(--space-10) var(--space-14);
      border-bottom: 1px solid var(--border);
    }
    /* Typography is the global .sb-label (v80 D3); only the UA margin is
       this component's business. */
    h2 { margin: 0; }
    .actions { display: flex; flex-wrap: wrap; align-items: baseline; gap: var(--space-8); }
    .body { padding: var(--space-14); }
    /* v179 §3.3 -- one gap to the first row: the body's padding, never the
       padding plus whatever top margin the first projected element brings
       (a <p>, a <dl>, a nested heading). .panel > .body is this component's
       own structure, so the reach is exactly one level. */
    :host ::ng-deep .panel > .body > :first-child { margin-top: 0; }
    /* Tables draw their own edge-to-edge padding. */
    .flush { padding: 0; }
    .panel-digest { margin: 0; padding: var(--space-10) var(--space-14); color: var(--text-secondary); font-size: var(--text-table); }
    .panel-problem { margin: 0; padding: var(--space-10) var(--space-14); color: var(--warn); font-size: var(--text-table); }
    .panel-toggle {
      min-height: var(--control-h);
      min-width: var(--control-h);
      background: none;
      border: 0;
      color: var(--text-faint);
      cursor: pointer;
    }
    .panel-toggle:hover { color: var(--text); }
  `,
})
export class Panel {
  readonly heading = input<string | null>(null);
  readonly flush = input(false);

  /** The narrowest viewport at which this panel renders in full — v95 §4.3. */
  readonly inlineFrom = input<Viewport | undefined>(undefined);
  /** One line answering the panel's own question. `null` means this panel has
   *  nothing worth saying in one line, and it therefore never collapses —
   *  v95 §4.3. A digest of '—' above a panel with real content is the defect
   *  this rule exists to prevent. */
  readonly digest = input<string | null>(null);
  /**
   * Why this panel must not be collapsed right now — v95 §5 guard 2.
   *
   * Stale data, a failed load, or a scope that makes the number
   * unrepresentative. Set, the panel force-expands, renders the reason, and
   * drops its toggle: a warning the user can fold back behind a digest that
   * does not mention it is a warning that does not exist.
   */
  readonly problem = input<string | null>(null);
  /** Test override — jsdom resolves no media query. */
  readonly viewportAt = input<Viewport | null>(null);

  protected readonly expanded = signal(false);

  private readonly viewportService = inject(ViewportService);
  private readonly viewport = computed<Viewport>(
    () => this.viewportAt() ?? this.viewportService.viewport(),
  );

  protected readonly collapsible = computed(
    () => this.problem() === null
      && this.digest() !== null
      && !isInline(this.inlineFrom(), this.viewport()),
  );

  protected readonly collapsed = computed(
    () => this.collapsible() && !this.expanded(),
  );
}

export interface Tab {
  id: string;
  label: string;
  /** Optional -- every existing caller (Trade detail's five tabs,
   *  Analytics' four) omits this and renders exactly as before. Set only
   *  by callers that want an icon rendered before the label AND, below
   *  `sm`, in PLACE of it (the label stays as the tab's accessible name
   *  via title/aria-label even when hidden visually) -- see
   *  positions-table.ts's lifecycle tabs. */
  icon?: IconName;
  /** Optional -- shown only alongside `icon`, and only below `md`, as
   *  "· N" next to the icon once the label text itself is hidden there
   *  (see positions-table.ts's per-status counts). A tab with no `icon`
   *  never renders this, regardless of whether it's set. */
  count?: number;
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
  imports: [Icon],
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
          [class.iconed]="!!tab.icon"
          [attr.aria-selected]="tab.id === active()"
          [attr.title]="tab.icon ? tab.label : null"
          [attr.aria-label]="tab.icon ? tab.label : null"
          [tabindex]="tab.id === active() ? 0 : -1"
          (click)="activeChange.emit(tab.id)"
        >
          @if (tab.icon) {
            <sb-icon [name]="tab.icon" />
          }
          <span class="label">{{ tab.label }}</span>
          @if (tab.icon && tab.count !== undefined) {
            <span class="count" aria-hidden="true">· {{ tab.count }}</span>
          }
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
      display: flex;
      align-items: center;
      gap: var(--space-6);
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
    .count { display: none; }
    /* On a phone an iconed tab swaps its words for the glyph plus "· N"
       (the label carried the count, so the count is shown separately). The
       label stays as the tab's accessible name via title/aria-label. Tablet
       and desktop keep icon + words. */
    @media (max-width: 639px) {
      .tab.iconed .label { display: none; }
      .tab.iconed .count { display: inline; }
      .tab.iconed { padding: var(--space-8) var(--space-10); }
    }
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
 * **`last baseline`, and the reason matters** (v179 §3.4; it was
 * `flex-end`). A labelled control is label-band + control-band; a bare
 * button is control-band only. Both END in a --control-h control with its
 * text centred, so their last baselines coincide exactly where their bottom
 * edges did -- the two still land on one line whatever the label does above.
 * Unlike `flex-end`, a plain text item in the row (the Versions "Running
 * now" label, a count, an N=) now sits on the controls' text line instead
 * of on their bottom border.
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
      align-items: last baseline;
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
 *
 * Its own close paths (the × button, Escape, a backdrop click) play an exit
 * first (spec v168 §3a): `requestClose()` sets `closing`, plays
 * `.sb-drawer-out` (a sinking sheet below 640px, styles/motion.css), and only
 * then closes the dialog, so the body stays mounted for the exit. Under Motion
 * Off or pending it closes at once, as before.
 */
@Component({
  selector: 'sb-drawer',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FocusTrap],
  template: `
    <!-- (cancel) is Escape: it is prevented and routed through requestClose()
         so the exit plays; the native close then fires (close) once. -->
    <dialog #dialog class="drawer elev-overlay" [class.sb-drawer-in]="!closing()"
            (close)="onClosed()" (cancel)="onCancel($event)" (click)="onDialogClick($event)">
      <!-- Only present while open, so sbFocusTrap's constructor/ngOnDestroy
           pair runs on exactly open and close -- see focus-trap.ts. -->
      @if (open()) {
        <div sbFocusTrap class="drawer-content">
          <div class="drag-handle" aria-hidden="true"></div>
          <header>
            <h2>{{ heading() }}</h2>
            <button type="button" class="close" aria-label="Close" (click)="requestClose()">×</button>
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
    /* v168 §3a: below 640px the drawer is a bottom sheet rising from the
       foot of the screen, with a drag handle and rounded top corners (its
       other edges sit flush, as on desktop); 640-1023px it is 85vw from the
       right; from 1024px the width above. */
    .drag-handle { display: none; }
    @media (max-width: 639px) {
      .drawer { margin: auto 0 0; width: 100vw; height: auto; max-height: 85dvh; }
      .drawer.elev-overlay { border-radius: var(--panel-radius) var(--panel-radius) 0 0; border-width: 1px 0 0; }
      .drag-handle { display: block; width: 36px; height: 4px; margin: var(--space-8) auto 0; border-radius: var(--radius-sm); background: var(--border-strong); }
    }
    @media (min-width: 640px) and (max-width: 1023px) {
      .drawer { width: 85vw; }
    }
  `,
})
export class Drawer {
  readonly open = input(false);
  readonly heading = input('');
  readonly closed = output<void>();

  protected readonly closing = signal(false);

  private readonly motion = inject(MotionService);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');
  private cancelExit: () => void = () => undefined;

  constructor() {
    effect(() => {
      const element = this.dialog().nativeElement;
      if (this.open() && !element.open) {
        untracked(() => this.stopExit());
        element.showModal();
      } else if (!this.open() && element.open) element.close();
    });
  }

  /** A click on the scrim lands on the dialog element itself; one inside the
   *  panel lands on a descendant. Checking the rect too keeps a click on the
   *  dialog's own (padding-free) surface from closing it. */
  protected onDialogClick(event: MouseEvent): void {
    const element = this.dialog().nativeElement;
    if (event.target !== element) return;
    const box = element.getBoundingClientRect();
    const inside = event.clientX >= box.left && event.clientX <= box.right
      && event.clientY >= box.top && event.clientY <= box.bottom;
    if (!inside) this.requestClose();
  }

  /** The × button, Escape and the backdrop: one path, exit first. */
  protected requestClose(): void {
    const element = this.dialog().nativeElement;
    if (this.closing() || !element.open) return;
    this.closing.set(true);
    this.cancelExit = playExit(element, 'sb-drawer-out', this.motion.active(), () => element.close());
  }

  protected onCancel(event: Event): void {
    event.preventDefault();
    this.requestClose();
  }

  /** The native close, whoever caused it: report it once. */
  protected onClosed(): void {
    this.stopExit();
    this.closed.emit();
  }

  private stopExit(): void {
    this.cancelExit();
    this.cancelExit = () => undefined;
    this.closing.set(false);
  }
}
