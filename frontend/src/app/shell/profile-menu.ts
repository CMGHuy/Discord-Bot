import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { Button } from '../ui/button';
import { Icon } from '../ui/icon';
import { MotionMode, parseMotion } from '../ui/motion/motion.service';
import { SegmentOption, Segmented } from '../ui/segmented';

/** The three Motion modes, in the order the control shows them (spec v168 §1). */
const MOTION_OPTIONS: SegmentOption[] = [
  { value: 'on', label: 'On' },
  { value: 'reduced', label: 'Reduced' },
  { value: 'off', label: 'Off' },
];

/**
 * The avatar, and what sits behind it — spec v18 Decision 8.
 *
 * This replaces the sidebar's own "Sign out" button rather than joining it.
 * Two sign-out controls is worse than either alone: the second one is the one
 * nobody maintains, and on a destructive action "which of these two is the
 * real one" is not a question to leave open.
 *
 * Closes on Escape and on a click anywhere outside, and returns focus to the
 * trigger when it does — a menu that closes while leaving focus on a
 * now-hidden item strands a keyboard user at the top of the document.
 */
@Component({
  selector: 'sb-profile-menu',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [Button, Icon, Segmented],
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(document:keydown.escape)': 'close()',
  },
  template: `
    <button
      sb-button
      variant="icon"
      #trigger
      type="button"
      class="avatar"
      [attr.aria-expanded]="open()"
      aria-haspopup="menu"
      [attr.aria-label]="label()"
      (click)="toggle($event)"
    >
      <img
        src="bot-profile.png"
        srcset="bot-profile.png 1x, bot-profile@2x.png 2x"
        alt=""
        width="24"
        height="24"
      />
    </button>

    @if (open()) {
      <div class="menu elev-overlay" role="menu">
        <span class="who">{{ username() || 'Signed in' }}</span>
        <button sb-button variant="ghost" type="button" role="menuitem"
                class="zoom"
                [attr.aria-label]="'Text size ' + zoom() + '%. Click to change.'"
                (click)="zoomCycled.emit()">
          <sb-icon name="expand" />
          <span>Aa {{ zoom() }}%</span>
        </button>
        <div class="motion-row" role="none">
          <span class="menu-label" aria-hidden="true">Motion</span>
          <sb-segmented
            class="motion-control"
            label="Motion"
            [options]="motionOptions"
            [value]="motion()"
            (valueChange)="onMotion($event)"
          />
        </div>
        <button sb-button variant="ghost" type="button" role="menuitem" (click)="signOut()">
          <sb-icon name="signout" />
          <span>Sign out</span>
        </button>
      </div>
    }
  `,
  styles: `
    :host { position: relative; display: inline-flex; }

    /* padding/border/line-height override the icon variant's defaults --
       a tight circle around the photo, not the variant's usual hit-target
       padding. border-radius is the shape; the variant doesn't set one. */
    .avatar {
      padding: 0;
      border: 0;
      border-radius: 50%;
      line-height: 0;
    }
    .avatar img { border-radius: 50%; display: block; }

    .menu {
      position: absolute;
      top: calc(100% + var(--space-6));
      right: 0;
      z-index: 20;
      min-width: 150px;
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      padding: var(--space-6);
    }
    .who {
      font-size: var(--text-chip);
      color: var(--text-secondary);
      padding: 0 var(--space-4);
    }
    /* justify-content/padding/font-size override the ghost variant's
       defaults (centred, roomy, table-sized) for a compact left-aligned
       menu row; the variant owns colour, hover and focus. */
    .menu button {
      justify-content: flex-start;
      padding: var(--space-4) var(--space-6);
      font-size: var(--text-body);
    }
    /* The Motion control is a segmented group, not a menu row: it keeps its
       own centred segments. The ".menu button" rule above does not reach
       them (emulated encapsulation scopes it to this template's own
       buttons), so nothing has to be undone here. */
    .motion-row {
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
      padding: var(--space-4) var(--space-6);
    }
    .menu-label {
      font-size: var(--text-chip);
      color: var(--text-secondary);
    }
    /* Spec v168 §1 and §5: 44px targets on touch. --control-h already gives
       the height on coarse pointers; this gives a short label like "On" the
       same width. */
    @media (pointer: coarse) {
      :host ::ng-deep .motion-control .segment { min-width: 44px; justify-content: center; }
    }
  `,
})
export class ProfileMenu {
  private readonly host: ElementRef<HTMLElement> = inject(ElementRef);

  readonly username = signal<string | null>(null);
  readonly signedOut = output<void>();
  readonly zoom = input<number>(100);
  readonly zoomCycled = output<void>();

  /** The current Motion mode, owned by the shell's MotionService. */
  readonly motion = input<MotionMode>('on');
  readonly motionChanged = output<MotionMode>();

  protected readonly motionOptions = MOTION_OPTIONS;

  /** Validated, not trusted: the segmented control hands back a string. */
  protected onMotion(value: string): void {
    this.motionChanged.emit(parseMotion(value));
  }

  protected readonly open = signal(false);

  protected readonly label = computed(() =>
    this.open() ? 'Close account menu' : 'Account menu',
  );

  protected toggle(event: MouseEvent): void {
    // Stops the document listener below from seeing this same click and
    // closing the menu in the same tick it was opened.
    event.stopPropagation();
    this.open.update((v) => !v);
  }

  protected close(): void {
    if (!this.open()) return;
    this.open.set(false);
    this.focusTrigger();
  }

  protected onDocumentClick(event: MouseEvent): void {
    if (!this.open()) return;
    if (!this.host.nativeElement.contains(event.target as Node)) this.close();
  }

  protected signOut(): void {
    this.open.set(false);
    this.signedOut.emit();
  }

  /** Focus goes back where it came from, or a keyboard user is left at the
   *  top of the document with no idea what happened. */
  private focusTrigger(): void {
    const trigger = this.host.nativeElement.querySelector<HTMLElement>('.avatar');
    trigger?.focus();
  }
}
