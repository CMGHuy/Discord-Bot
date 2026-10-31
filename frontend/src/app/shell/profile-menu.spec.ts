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
    const signOut = Array.from(el.querySelectorAll<HTMLButtonElement>('[role=menuitem]'))
      .find((b) => b.textContent?.includes('Sign out'))!;
    signOut.click();
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

  it('offers the text-size control inside the menu and emits on click', () => {
    const f = TestBed.createComponent(ProfileMenu);
    f.componentRef.setInput('zoom', 110);
    f.detectChanges();

    const menuEl = f.nativeElement as HTMLElement;
    // Closed, the control is not in the DOM at all.
    expect(menuEl.querySelector('.zoom')).toBeNull();

    menuEl.querySelector<HTMLButtonElement>('.avatar')!.click();
    f.detectChanges();

    const zoom = menuEl.querySelector<HTMLButtonElement>('.zoom')!;
    expect(zoom.textContent?.trim()).toBe('Aa 110%');

    let cycled = 0;
    f.componentInstance.zoomCycled.subscribe(() => (cycled += 1));
    zoom.click();
    expect(cycled).toBe(1);
  });

  describe('Motion control (v168 §1)', () => {
    const control = () => el.querySelector('sb-segmented.motion-control');
    const segments = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('sb-segmented.motion-control .segment'));

    it('offers On, Reduced and Off under the label "Motion"', () => {
      openMenu();
      expect(control()).not.toBeNull();
      expect(control()!.querySelector('[role=group]')!.getAttribute('aria-label')).toBe('Motion');
      expect(segments().map((b) => b.textContent!.trim())).toEqual(['On', 'Reduced', 'Off']);
    });

    it('marks the current mode from the motion input', () => {
      fixture.componentRef.setInput('motion', 'reduced');
      openMenu();
      const current = segments().filter((b) => b.getAttribute('aria-pressed') === 'true');
      expect(current.map((b) => b.textContent!.trim())).toEqual(['Reduced']);
    });

    it('defaults to On when no mode is bound', () => {
      openMenu();
      const current = segments().find((b) => b.getAttribute('aria-pressed') === 'true');
      expect(current!.textContent!.trim()).toBe('On');
    });

    it('emits the chosen mode and keeps the menu open', () => {
      const chosen: string[] = [];
      fixture.componentInstance.motionChanged.subscribe((mode) => chosen.push(mode));
      openMenu();
      segments()[2].click();
      fixture.detectChanges();
      expect(chosen).toEqual(['off']);
      expect(menu()).not.toBeNull();
    });

    it('is keyboard-operable: ArrowRight moves to the next mode', () => {
      const chosen: string[] = [];
      fixture.componentInstance.motionChanged.subscribe((mode) => chosen.push(mode));
      openMenu();
      control()!.querySelector('[role=group]')!.dispatchEvent(
        new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }),
      );
      fixture.detectChanges();
      expect(chosen).toEqual(['reduced']);
    });
  });

  describe('Density control (v195 §1.4)', () => {
    const control = () => el.querySelector('sb-segmented.density-control');
    const segments = () =>
      Array.from(el.querySelectorAll<HTMLButtonElement>('sb-segmented.density-control .segment'));

    it('offers Dense and Comfortable under the label "Density"', () => {
      openMenu();
      expect(control()!.querySelector('[role=group]')!.getAttribute('aria-label')).toBe('Density');
      expect(segments().map((b) => b.textContent!.trim())).toEqual(['Dense', 'Comfortable']);
    });

    it('defaults to Dense and marks the density it is given', () => {
      openMenu();
      expect(segments().find((b) => b.getAttribute('aria-pressed') === 'true')!.textContent!.trim()).toBe('Dense');
      fixture.componentRef.setInput('density', 'comfortable');
      fixture.detectChanges();
      expect(segments().find((b) => b.getAttribute('aria-pressed') === 'true')!.textContent!.trim()).toBe('Comfortable');
    });

    it('emits the chosen density and keeps the menu open', () => {
      const chosen: string[] = [];
      fixture.componentInstance.densityChanged.subscribe((density) => chosen.push(density));
      openMenu();
      segments()[1].click();
      fixture.detectChanges();
      expect(chosen).toEqual(['comfortable']);
      expect(menu()).not.toBeNull();
    });

    it('says the touch rules win, so a phone or tablet user is not left guessing', () => {
      openMenu();
      expect(el.querySelector('.density-row .menu-note')!.textContent!.trim())
        .toBe('Desktop only: touch screens keep 44px rows.');
    });
  });
});

describe('ProfileMenu bot-status halo', () => {
  beforeEach(() => TestBed.configureTestingModule({ providers: [provideZonelessChangeDetection()] }));
  const halo = (state: 'live' | 'dead', botAlive: boolean | null, marketActive: boolean | null = true) => {
    const fixture = TestBed.createComponent(ProfileMenu);
    fixture.componentRef.setInput('state', state);
    fixture.componentRef.setInput('botAlive', botAlive);
    fixture.componentRef.setInput('marketActive', marketActive);
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).querySelector('.halo')!;
  };

  it('is green when live and the bot is alive', () => expect(halo('live', true).classList.contains('up')).toBe(true));
  it('is red when the bot is offline, even on a dead stream', () => expect(halo('dead', false).classList.contains('down')).toBe(true));
  it('draws nothing while the bot status is unknown', () => {
    const classes = halo('live', null).classList;
    expect(classes.contains('up') || classes.contains('down')).toBe(false);
  });
  it('stops blinking while the market is closed', () => expect(halo('live', true, false).classList.contains('resting')).toBe(true));
});
