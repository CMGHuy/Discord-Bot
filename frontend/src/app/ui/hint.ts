import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  effect,
  inject,
  input,
  signal,
} from '@angular/core';

let nextId = 0;

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
  },
  template: `
    <button
      type="button"
      class="trigger"
      [attr.aria-label]="label()"
      [attr.aria-expanded]="open()"
      [attr.aria-describedby]="id"
      (click)="toggle()"
    >
      <span class="glyph" aria-hidden="true">i</span>
    </button>
    <span
      class="pop elev-overlay"
      role="tooltip"
      [id]="id"
      [hidden]="!open()"
      [style.top.px]="popTop()"
      [style.left.px]="popLeft()"
    >{{ text() }}</span>
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
    /* position: fixed, not absolute -- an sb-panel body clips overflow
       (layout.ts's .panel { overflow: hidden }), which is everywhere this
       component gets used, so a panel-relative popover was invisible under
       its own trigger (v80 F26 browser walk). popTop/popLeft measure the
       trigger's own viewport rect instead of trusting an ancestor's box. */
    .pop {
      position: fixed;
      z-index: 20;
      width: max-content;
      max-width: min(280px, 90vw);
      padding: var(--space-8) var(--space-10);
      transform: translateX(-50%);
      color: var(--text);
      font-size: var(--text-chip);
      line-height: 1.5;
      text-align: left;
      white-space: normal;
    }
    /* A fingertip needs 44px around a 14px glyph (v80 D4). */
    @media (pointer: coarse), (max-width: 639px) {
      .trigger { min-width: var(--control-h); min-height: var(--control-h); }
    }
  `,
})
export class Hint {
  readonly text = input.required<string>();
  /** The trigger's accessible name. Name what it explains: "About expectancy". */
  readonly label = input('More information');

  protected readonly id = `sb-hint-${nextId++}`;
  protected readonly pinned = signal(false);
  protected readonly hovered = signal(false);
  protected readonly focused = signal(false);
  protected readonly open = computed(() => this.pinned() || this.hovered() || this.focused());

  protected readonly popTop = signal(0);
  protected readonly popLeft = signal(0);

  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private readonly reposition = (): void => {
    const trigger = this.host.querySelector('.trigger');
    if (!trigger) return;
    const rect = trigger.getBoundingClientRect();
    this.popTop.set(rect.bottom + 4);
    this.popLeft.set(rect.left + rect.width / 2);
  };

  constructor() {
    /** Fixed positioning (see the .pop comment) tracks the trigger's own
     *  rect, not the flow, so it has to be told explicitly: once on open,
     *  and on every scroll/resize while open -- a panel body scrolls its
     *  content (layout.ts's .body { overflow-y: auto }) without moving the
     *  window, which a plain window-resize listener would miss. */
    effect((onCleanup) => {
      if (!this.open()) return;
      this.reposition();
      window.addEventListener('scroll', this.reposition, { capture: true, passive: true });
      window.addEventListener('resize', this.reposition, { passive: true });
      onCleanup(() => {
        window.removeEventListener('scroll', this.reposition, true);
        window.removeEventListener('resize', this.reposition);
      });
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
}
