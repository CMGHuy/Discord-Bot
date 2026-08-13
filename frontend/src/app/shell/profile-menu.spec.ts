import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideZonelessChangeDetection } from '@angular/core';
import { beforeEach, describe, expect, it } from 'vitest';

import { ProfileMenu } from './profile-menu';

describe('ProfileMenu', () => {
  let fixture: ComponentFixture<ProfileMenu>;
  let el: HTMLElement;

  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] });
    fixture = TestBed.createComponent(ProfileMenu);
    fixture.detectChanges();
    el = fixture.nativeElement as HTMLElement;
  });

  const trigger = () => el.querySelector('.avatar') as HTMLButtonElement;
  const menu = () => el.querySelector('[role=menu]');

  function openMenu() {
    trigger().click();
    fixture.detectChanges();
  }

  it('opens on the avatar', () => {
    expect(menu()).toBeNull();
    openMenu();
    expect(menu()).not.toBeNull();
    expect(trigger().getAttribute('aria-expanded')).toBe('true');
  });

  it('closes on Escape', () => {
    openMenu();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();
    expect(menu()).toBeNull();
  });

  it('closes on a click outside', () => {
    openMenu();
    document.body.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    fixture.detectChanges();
    expect(menu()).toBeNull();
  });

  it('stays open when the click is inside it', () => {
    // The document listener sees every click; without a containment check it
    // would close the menu the moment someone reached for an item.
    openMenu();
    (menu() as HTMLElement).dispatchEvent(new MouseEvent('click', { bubbles: true }));
    fixture.detectChanges();
    expect(menu()).not.toBeNull();
  });

  it('emits signedOut from the menu item', () => {
    const emitted: unknown[] = [];
    fixture.componentInstance.signedOut.subscribe(() => emitted.push(true));
    openMenu();
    (el.querySelector('[role=menuitem]') as HTMLButtonElement).click();
    fixture.detectChanges();
    expect(emitted).toHaveLength(1);
    expect(menu()).toBeNull();
  });

  it('returns focus to the trigger when it closes', () => {
    // A menu that closes leaving focus on a now-removed item strands a
    // keyboard user at the top of the document.
    openMenu();
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    fixture.detectChanges();
    expect(document.activeElement).toBe(trigger());
  });
});
