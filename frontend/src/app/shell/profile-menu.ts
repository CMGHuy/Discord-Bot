import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  output,
  signal,
} from '@angular/core';

import { Icon } from '../ui/icon';

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
  imports: [Icon],
  host: {
    '(document:click)': 'onDocumentClick($event)',
    '(document:keydown.escape)': 'close()',
  },
  template: `
    <button
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
      <div class="menu" role="menu">
        <span class="who">{{ username() || 'Signed in' }}</span>
        <button type="button" role="menuitem" (click)="signOut()">
          <sb-icon name="signout" />
          <span>Sign out</span>
        </button>
      </div>
    }
  `,
  styles: `
    :host { position: relative; display: inline-flex; }

    .avatar {
      display: inline-flex;
      padding: 0;
      border: 0;
      background: none;
      border-radius: 50%;
      cursor: pointer;
      line-height: 0;
    }
    .avatar img { border-radius: 50%; display: block; }
    .avatar:focus-visible { outline: 1px solid var(--accent); outline-offset: 2px; }

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
      background: var(--surface-raised);
      border: 1px solid var(--border);
      border-radius: var(--radius);
    }
    .who {
      font-size: var(--text-chip);
      color: var(--text-secondary);
      padding: 0 var(--space-4);
    }
    .menu button {
      display: flex;
      align-items: center;
      gap: var(--space-6);
      padding: var(--space-4) var(--space-6);
      background: none;
      border: 0;
      border-radius: var(--radius);
      color: var(--text);
      font-size: var(--text-body);
      text-align: left;
      cursor: pointer;
    }
    .menu button:hover { background: var(--surface); }
    .menu button:focus-visible { outline: 1px solid var(--accent); outline-offset: -1px; }
  `,
})
export class ProfileMenu {
  private readonly host: ElementRef<HTMLElement> = inject(ElementRef);

  readonly username = signal<string | null>(null);
  readonly signedOut = output<void>();

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
