import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  effect,
  input,
  output,
  viewChild,
} from '@angular/core';

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
          <h2>{{ text }}</h2>
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
    h2 {
      color: var(--text-secondary);
      font-size: var(--text-micro);
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.1em;
    }
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
  template: `
    <div class="tabs" role="tablist" (keydown)="onKeydown($event)">
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
  `,
  styles: `
    .tabs { display: flex; gap: var(--space-4); border-bottom: 1px solid var(--border); }
    .tab {
      padding: var(--space-8) var(--space-14);
      background: none;
      border: 0;
      border-bottom: 2px solid transparent;
      color: var(--text-secondary);
      font: inherit;
      font-size: var(--text-table);
      font-weight: 600;
      cursor: pointer;
      transition: color var(--transition), border-color var(--transition);
    }
    .tab:hover { color: var(--text); }
    .tab:focus-visible { outline: 1px solid var(--accent); outline-offset: -2px; }
    .active { color: var(--text); border-bottom-color: var(--accent); }
  `,
})
export class TabBar {
  readonly tabs = input.required<Tab[]>();
  readonly active = input.required<string>();
  readonly activeChange = output<string>();

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
 * `stacked` collapses the row to a full-width column below `sm` (640px).
 * `scan-tab`'s kill row hand-rolled exactly this; it belongs here instead.
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
      .stacked { flex-direction: column; align-items: stretch; }
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
  template: `
    <dialog #dialog class="drawer" (close)="closed.emit()" (cancel)="closed.emit()">
      <header>
        <h2>{{ heading() }}</h2>
        <button type="button" class="close" aria-label="Close" (click)="dismiss()">×</button>
      </header>
      <div class="body"><ng-content /></div>
    </dialog>
  `,
  styles: `
    .drawer {
      width: min(480px, 100vw);
      max-width: none;
      height: 100vh;
      max-height: 100vh;
      margin: 0 0 0 auto;
      padding: 0;
      background: var(--surface);
      border: 0;
      border-left: 1px solid var(--border-strong);
      color: var(--text);
    }
    .drawer::backdrop { background: rgb(0 0 0 / 0.5); }

    header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: var(--space-14);
      border-bottom: 1px solid var(--border);
    }
    h2 { font-size: var(--text-subhead); font-weight: 600; }
    .close {
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
