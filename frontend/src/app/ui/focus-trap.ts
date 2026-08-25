import { Directive, ElementRef, HostListener, OnDestroy, OnInit, inject } from '@angular/core';

/** Elements a keyboard user can land on. `[tabindex]:not([tabindex="-1"])`
 *  excludes the programmatic-only stops route-focus.ts creates -- those are
 *  destinations, not tab STOPS. */
const FOCUSABLE =
  'a[href], button:not([disabled]), textarea:not([disabled]), ' +
  'input:not([disabled]), select:not([disabled]), ' +
  '[tabindex]:not([tabindex="-1"])';

/**
 * Trap Tab within the host while it exists, and restore focus on removal.
 *
 * Built for a host that is structurally added and removed (`@if`), which is
 * what both `sb-drawer` and `sb-confirm-dialog` do for their panel content:
 * the ADD is the open, the REMOVE is the close, and the constructor /
 * `ngOnDestroy` pair below is what runs on exactly those two events. That
 * timing also has to fit around each host's own `showModal()`/`close()`
 * effect -- confirmed empirically (see the plan's Task 41 note) that a
 * component's own `effect()` runs before its template's `@if` materialises
 * a new child view, so `showModal()` has already made the dialog visible by
 * the time this constructor asks to focus into it.
 */
@Directive({ selector: '[sbFocusTrap]' })
export class FocusTrap implements OnInit, OnDestroy {
  private readonly host = inject(ElementRef<HTMLElement>).nativeElement as HTMLElement;
  private readonly previouslyFocused = document.activeElement as HTMLElement | null;

  // ngOnInit, not the constructor: at construction time the host element has
  // been created but is not yet spliced into the connected DOM tree, and a
  // browser silently no-ops a focus() call on a disconnected node. By
  // ngOnInit the view has been inserted, so focus actually lands.
  ngOnInit(): void {
    const first = this.host.querySelector<HTMLElement>(FOCUSABLE);
    if (first) first.focus();
    else this.host.focus();
  }

  ngOnDestroy(): void {
    this.previouslyFocused?.focus();
  }

  @HostListener('keydown', ['$event'])
  protected onKeydown(event: KeyboardEvent): void {
    if (event.key !== 'Tab') return;
    const focusable = [...this.host.querySelectorAll<HTMLElement>(FOCUSABLE)];
    if (focusable.length === 0) return;

    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
}
