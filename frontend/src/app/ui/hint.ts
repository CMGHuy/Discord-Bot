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

let nextId = 0;

/**
 * Whether this engine has the Popover API (spec v194 A1, feature detection).
 * Without it the hint keeps the old position: fixed path, so an old browser
 * loses only the cases an ancestor transform clips -- never every hint.
 */
export function supportsPopover(): boolean {
  return typeof HTMLElement !== 'undefined' && typeof HTMLElement.prototype.showPopover === 'function';
}


/** Space between the trigger and the popover, either side. */
const POP_GAP = 4;

const clamp = (value: number, min: number, max: number): number => Math.max(min, Math.min(value, max));

/**
 * Where an open popover goes (spec v194 A1): 4px under its trigger, flipped
 * above when it would cross the bottom margin and there is room above (or
 * more room above than below), and shifted sideways rather than run off
 * either edge -- `margin` px from every viewport edge, the top and left
 * margins winning for a popover larger than the viewport. `left` is the
 * popover's own left edge. Pure: jsdom has no layout, so this is the part of
 * the geometry a unit test can prove; the layout audit's `hint` check proves
 * the rest in a browser.
 */
export function clampPopover(
  trigger: { top: number; bottom: number; left: number; right: number; width: number },
  pop: { width: number; height: number },
  viewport: { width: number; height: number },
  align: 'center' | 'left',
  margin = 8,
): { top: number; left: number; above: boolean } {
  const fitsBelow = trigger.bottom + POP_GAP + pop.height <= viewport.height - margin;
  const fitsAbove = trigger.top - POP_GAP - pop.height >= margin;
  const above = !fitsBelow && (fitsAbove || trigger.top > viewport.height - trigger.bottom);
  const rawTop = above ? trigger.top - POP_GAP - pop.height : trigger.bottom + POP_GAP;
  const rawLeft = align === 'left' ? trigger.right - pop.width : trigger.left + trigger.width / 2 - pop.width / 2;
  return {
    top: clamp(rawTop, margin, viewport.height - margin - pop.height),
    left: clamp(rawLeft, margin, viewport.width - margin - pop.width),
    above,
  };
}


/** Fired (non-bubbling) on a modal <dialog> host the moment it starts to
 *  close -- sb-drawer and sb-confirm-dialog, from requestClose(). A hint
 *  inside listens and closes, because a pinned manual popover is not hidden
 *  by its ancestor dialog closing and would stay painted through the exit. */
export const DIALOG_CLOSING_EVENT = 'sb-dialog-closing';

/**
 * Where an anchor-mode label goes (v195 correction 10): to the right of its
 * anchor, two gaps off it, vertically centred on it, and kept `margin` px
 * inside the viewport -- shifted up off the bottom edge, down off the top,
 * left off the right. A rail label under its 48px icon would cover the next
 * entry, so it goes beside. Pure, like clampPopover.
 */
export function placeBeside(
  anchor: { top: number; bottom: number; left: number; right: number; width: number },
  pop: { width: number; height: number },
  viewport: { width: number; height: number },
  margin = 8,
): { top: number; left: number } {
  const centre = (anchor.top + anchor.bottom) / 2;
  return {
    top: clamp(centre - pop.height / 2, margin, viewport.height - margin - pop.height),
    left: clamp(anchor.right + 2 * POP_GAP, margin, viewport.width - margin - pop.width),
  };
}

/**
 * An info popover -- spec v80 D4.
 *
 * Thirty-five `title` tooltips carry real explanation today, and a `title`
 * opens only on mouse hover: a phone never shows it and a keyboard user never
 * reaches it. This opens on hover, on keyboard focus and on tap, and closes on
 * Escape or a tap anywhere else. Phone screens adopts it.
 *
 * Three reasons to be open, kept separate so one ending cannot close a hint
 * another still holds. Hover and focus hold it only while they last. A click
 * PINS it; a click on a pinned hint closes it. The order matters on a phone:
 * a tap fires an emulated mouseenter and a focus BEFORE its click, so a plain
 * toggle would open on the hover and close again on the click.
 *
 * The trigger is a real button with `aria-expanded`, and the popover is
 * `role="tooltip"` referenced by `aria-describedby`, so a screen reader reads
 * the text on focus without opening anything.
 *
 * Since v194 the popover is a native `popover="manual"` element shown with
 * `showPopover()`: the browser paints it in the top layer, outside every
 * ancestor's containing block, overflow clip and stacking context. An
 * `.sb-lift` card's hover transform (`motion.css`) made the old
 * `position: fixed` popover position against the card and clip with it,
 * which is how a hint on a tile or panel heading opened invisibly. `open`
 * stays the single source of truth; the effect below maps it onto the API,
 * guarded, because engines throw `InvalidStateError` on a double show or
 * hide.
 *
 * Anchor (label) mode, v195 correction 10: with `anchor` set, no trigger is
 * rendered and the popover labels that element instead -- a rail link, which
 * cannot contain a button. The anchor's own hover and focus open it, Escape
 * on the anchor closes it, the anchor is described by it, and it sits beside
 * the anchor (placeBeside) as a one-line label. Everything else -- the top
 * layer, the guards, the dialog-close rule -- is the same machinery.
 */
@Component({
  selector: 'sb-hint',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: {
    '(mouseenter)': 'hovered.set(true)',
    '(mouseleave)': 'hovered.set(false)',
    '(focusin)': 'focused.set(true)',
    '(focusout)': 'onFocusOut($event)',
    '(keydown.escape)': 'close()',
    '(document:pointerdown)': 'onDocumentPointer($event)',
    '[class.anchored]': 'anchor() !== null',
  },
  template: `
    @if (!anchor()) {
    <button
      type="button"
      class="trigger"
      [attr.aria-label]="label()"
      [attr.aria-expanded]="open()"
      [attr.aria-describedby]="id"
      (click)="toggle()"
    >
      <span class="glyph" aria-hidden="true">{{ glyph() }}</span>
    </button>
    }
    <span
      #pop
      class="pop elev-overlay"
      [class.wide]="wide()"
      [class.xl]="xl()"
      [class.label]="anchor() !== null"
      [class.fallback-closed]="!native && !open()"
      [attr.popover]="native ? 'manual' : null"
      role="tooltip"
      [id]="id"
      [style.top.px]="popTop()"
      [style.left.px]="popLeft()"
    >@if (text()) {
      {{ text() }}
    } @else {
      <ng-content />
    }</span>
  `,
  styles: `
    :host { position: relative; display: inline-flex; vertical-align: middle; }
    .trigger {
      display: inline-grid;
      place-items: center;
      padding: 0;
      background: none;
      border: 0;
      color: var(--text-muted);
      cursor: help;
    }
    .trigger:hover, .trigger[aria-expanded='true'] { color: var(--text); }
    .trigger:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }
    .glyph {
      display: inline-grid;
      place-items: center;
      width: 14px;
      height: 14px;
      border: 1px solid currentColor;
      border-radius: 50%;
      font-family: var(--font-mono);
      font-size: var(--text-micro);
      line-height: 1;
    }
    /* Native path (v194 A1): popover="manual" puts this box in the top
       layer, whose containing block is the viewport whatever the ancestors
       do, so popTop/popLeft -- measured from the trigger's viewport rect --
       are exact. The UA's [popover] rules (inset: 0, margin: auto,
       overflow: auto) are reset here; .elev-overlay's border and background
       are author styles and already win over the UA's. Fallback path (no
       Popover API): the same position: fixed box, which an ancestor
       transform can still clip -- the pre-v194 behaviour, hidden by
       .fallback-closed instead of the UA's popover display rule. */
    .pop {
      position: fixed;
      inset: auto;
      margin: 0;
      overflow: visible;
      z-index: 20;
      width: max-content;
      max-width: min(280px, 90vw);
      padding: var(--space-8) var(--space-10);
      color: var(--text);
      font-size: var(--text-chip);
      line-height: 1.5;
      text-align: left;
      white-space: normal;
    }
    .pop.fallback-closed { display: none; }
    /* Anchor mode (v195 correction 10): the host has no box of its own -- the
       label lives in the top layer beside its anchor -- and the popover is a
       one-line name, not an explanation. */
    :host(.anchored) { display: contents; }
    .pop.label { padding: var(--space-4) var(--space-8); font-size: var(--text-table); white-space: nowrap; }
    .pop.wide { max-width: min(420px, 90vw); }
    /* 50% past .wide, on request (2026-09-14) -- for a hint whose content
       (a diagram, not a sentence) reads as cramped even at .wide's 420px. */
    .pop.xl { max-width: min(630px, 90vw); font-size: var(--text-table); }
    /* No transform: popLeft is the popover's own left edge, already
       centred (or right-aligned for align="left") and clamped inside the
       viewport by clampPopover() -- see reposition() below. */
    /* A fingertip needs 44px around a 14px glyph (v80 D4; phone and tablet
       since v179). */
    @media (pointer: coarse), (max-width: 1023px) {
      .trigger { min-width: var(--control-h); min-height: var(--control-h); }
    }
  `,
})
export class Hint {
  /** Plain-text hints use text; richer explanatory content can be projected. */
  readonly text = input('');
  /** The trigger's accessible name. Name what it explains: "About expectancy". */
  readonly label = input('More information');
  /** Default to the familiar information glyph; a nearby question can opt in. */
  readonly glyph = input('i');
  /** Use the larger overlay only for a compact, non-interactive diagram. */
  readonly wide = input(false);
  /** 50% larger again than `wide` -- for content that is cramped even
   *  there. Takes precedence over `wide` when both are set. */
  readonly xl = input(false);
  /** 'center' (default) sits the popover under the trigger's midpoint;
   *  'left' ends it at the trigger's right edge instead. Since v194 the
   *  viewport clamp keeps either inside the screen, so 'left' is no longer
   *  needed to stop a popover running off an edge; the input stays for the
   *  callers that set it. */
  readonly align = input<'center' | 'left'>('center');
  /** Anchor (label) mode, v195 correction 10: the element this hint labels.
   *  Non-null renders no trigger; the anchor's hover and focus open the
   *  popover, which sits beside it. Null (default) is the glyph trigger. */
  readonly anchor = input<HTMLElement | null>(null);

  protected readonly id = `sb-hint-${nextId++}`;
  protected readonly pinned = signal(false);
  protected readonly hovered = signal(false);
  protected readonly focused = signal(false);
  protected readonly open = computed(() => this.pinned() || this.hovered() || this.focused());

  /** Read once: an engine does not gain or lose the Popover API mid-session. */
  protected readonly native = supportsPopover();
  private readonly pop = viewChild.required<ElementRef<HTMLElement>>('pop');
  /** This instance showed its popover and has not hidden it yet. Tracked
   *  here rather than read back from :popover-open, so the guards hold the
   *  same way under the test polyfill (jsdom cannot match that selector). */
  private shown = false;

  protected readonly popTop = signal(0);
  protected readonly popLeft = signal(0);

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private readonly reposition = (): void => {
    const anchor = this.anchor();
    const target = anchor ?? this.host.querySelector('.trigger');
    if (!target) return;
    const pop = this.pop().nativeElement;
    const root = document.documentElement;
    const rect = target.getBoundingClientRect();
    const size = { width: pop.offsetWidth, height: pop.offsetHeight };
    const viewport = { width: root.clientWidth, height: root.clientHeight };
    // Anchor mode labels beside its anchor; the glyph trigger opens below.
    const place = anchor ? placeBeside(rect, size, viewport) : clampPopover(rect, size, viewport, this.align());
    this.popTop.set(place.top);
    this.popLeft.set(place.left);
  };

  constructor() {
    /** Open -> show the popover (top layer, or the fallback's fixed box),
     *  then place it from the trigger's viewport rect: once on open, and on
     *  every scroll/resize while open -- a panel body scrolls its content
     *  (layout.ts's .body { overflow-y: auto }) without moving the window,
     *  which a plain window-resize listener would miss. Closed -> the
     *  cleanup hides it. */
    effect((onCleanup) => {
      if (!this.open()) return;
      const pop = this.pop().nativeElement;
      this.show(pop);
      this.reposition();
      const frame = requestAnimationFrame(this.reposition);
      const unwatch = this.watchHostDialog();
      window.addEventListener('scroll', this.reposition, { capture: true, passive: true });
      window.addEventListener('resize', this.reposition, { passive: true });
      onCleanup(() => {
        cancelAnimationFrame(frame);
        unwatch();
        window.removeEventListener('scroll', this.reposition, true);
        window.removeEventListener('resize', this.reposition);
        this.hide(pop);
      });
    });

    /** Anchor mode: bind the anchor's events for as long as it is set, and
     *  unbind (closing the label) when it changes or goes away. */
    effect((onCleanup) => {
      const anchor = this.anchor();
      if (anchor) onCleanup(this.bindAnchor(anchor));
    });
  }

  protected toggle(): void {
    if (this.pinned()) this.close();
    else this.pinned.set(true);
  }

  protected close(): void {
    this.pinned.set(false);
    this.hovered.set(false);
    this.focused.set(false);
  }

  /** Focus moving between the trigger and anything inside the popover is not
   *  focus leaving the hint. */
  protected onFocusOut(event: FocusEvent): void {
    const next = event.relatedTarget as Node | null;
    if (!next || !this.host.contains(next)) this.focused.set(false);
  }

  protected onDocumentPointer(event: Event): void {
    if (!this.host.contains(event.target as Node)) this.close();
  }

  /** Guarded (v194 A1): showPopover() throws InvalidStateError on a
   *  disconnected or already-open popover on some engines. */
  private show(pop: HTMLElement): void {
    if (!this.native || this.shown || !pop.isConnected) return;
    pop.showPopover();
    this.shown = true;
  }

  /** Guarded the same way. A popover removed from the document was already
   *  hidden by the browser, so only a connected one is hidden here. */
  private hide(pop: HTMLElement): void {
    if (!this.shown) return;
    this.shown = false;
    if (pop.isConnected) pop.hidePopover();
  }


  /** A hint inside a modal <dialog> host (sb-drawer, sb-confirm-dialog)
   *  closes when that dialog starts closing (v194 A1). A pinned manual
   *  popover is not hidden by its ancestor dialog closing, so it would stay
   *  painted in the top layer through the drawer's exit animation. `close`
   *  covers a host shut without its exit (the drawer's [open] input going
   *  false). Looked up on open, not in the constructor: a projected hint is
   *  not inside its dialog yet when it is created. Returns the remover. */
  private watchHostDialog(): () => void {
    const dialog = this.host.closest('dialog');
    if (!dialog) return () => undefined;
    const onClosing = (): void => this.close();
    dialog.addEventListener(DIALOG_CLOSING_EVENT, onClosing);
    dialog.addEventListener('close', onClosing);
    return () => {
      dialog.removeEventListener(DIALOG_CLOSING_EVENT, onClosing);
      dialog.removeEventListener('close', onClosing);
    };
  }

  /** Anchor mode (v195 correction 10): the anchor's hover and focus feed the
   *  same hovered/focused signals the glyph trigger does, Escape on it
   *  dismisses the label without moving focus (WCAG 1.4.13), and the anchor
   *  -- not a trigger of ours -- is described by the popover. Returns the
   *  remover, which also closes the label. */
  private bindAnchor(anchor: HTMLElement): () => void {
    // A press closes the label (the click is about to act on the link), and
    // the focus the browser then gives the link must not reopen it: it would
    // stay beside the link, after navigation, until blur. Only that one
    // focus is swallowed; blur or a key press clears the flag, so a later
    // keyboard focus still labels the link.
    let pressed = false;
    const onKey = (event: Event): void => {
      pressed = false;
      if ((event as KeyboardEvent).key === 'Escape') this.close();
    };
    const listeners: [string, EventListener][] = [
      ['mouseenter', () => this.hovered.set(true)],
      ['mouseleave', () => this.hovered.set(false)],
      ['pointerdown', () => { pressed = true; this.close(); }],
      ['focus', () => { if (!pressed) this.focused.set(true); pressed = false; }],
      ['blur', () => { pressed = false; this.focused.set(false); }],
      ['keydown', onKey],
    ];
    for (const [type, listener] of listeners) anchor.addEventListener(type, listener);
    anchor.setAttribute('aria-describedby', this.id);
    return () => {
      for (const [type, listener] of listeners) anchor.removeEventListener(type, listener);
      if (anchor.getAttribute('aria-describedby') === this.id) anchor.removeAttribute('aria-describedby');
      this.close();
    };
  }
}
